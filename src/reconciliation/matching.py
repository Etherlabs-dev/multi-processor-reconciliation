"""Explainable candidate scoring, ambiguity controls, and bounded split matching."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import asdict
from decimal import ROUND_HALF_UP, Decimal
from hashlib import sha256
from itertools import combinations

from reconciliation.models import (
    Candidate,
    CanonicalRecord,
    Discrepancy,
    Match,
    ReconciliationConfig,
    ReconciliationResult,
    RecordKind,
)

SCORE_QUANTUM = Decimal("0.0001")
REFUND_KINDS = {RecordKind.REFUND, RecordKind.REVERSAL}


def _compatible_kinds(left: RecordKind, right: RecordKind) -> bool:
    if left in REFUND_KINDS or right in REFUND_KINDS:
        return left in REFUND_KINDS and right in REFUND_KINDS
    if left == RecordKind.FEE or right == RecordKind.FEE:
        return left == right
    return True


def score_candidate(
    left: CanonicalRecord,
    right: CanonicalRecord,
    config: ReconciliationConfig | None = None,
) -> Candidate | None:
    """Score an eligible pair; currency, amount, date, and type are hard controls."""

    config = config or ReconciliationConfig()
    if left.source != right.source or left.account_id != right.account_id:
        return None
    if left.currency != right.currency or not _compatible_kinds(left.kind, right.kind):
        return None
    amount_difference = abs(left.net_amount - right.net_amount)
    if amount_difference > config.amount_tolerance:
        return None
    date_difference = abs((left.occurred_at.date() - right.occurred_at.date()).days)
    if date_difference > config.date_window_days:
        return None

    if config.amount_tolerance == 0:
        amount_score = Decimal("0.65")
    else:
        amount_ratio = amount_difference / config.amount_tolerance
        amount_score = Decimal("0.55") + (Decimal("0.10") * (Decimal("1") - amount_ratio))
    if config.date_window_days == 0:
        date_score = Decimal("0.20")
    else:
        date_score = Decimal("0.20") * (
            Decimal("1") - (Decimal(date_difference) / Decimal(config.date_window_days))
        )
    score = amount_score + date_score + Decimal("0.05")
    evidence = ["source_account", "currency", "amount", "date_window", "compatible_type"]

    references = {value for value in (left.reference, left.external_id) if value}
    right_references = {value for value in (right.reference, right.external_id) if value}
    if references & right_references:
        score += Decimal("0.15")
        evidence.append("reference")

    return Candidate(
        left_id=left.idempotency_key,
        right_id=right.idempotency_key,
        score=min(score, Decimal("1.00")).quantize(SCORE_QUANTUM, rounding=ROUND_HALF_UP),
        amount_difference=amount_difference,
        date_difference_days=date_difference,
        evidence=tuple(evidence),
    )


def _match_classification(left: CanonicalRecord, right: CanonicalRecord, candidate: Candidate) -> str:
    if left.kind in REFUND_KINDS or right.kind in REFUND_KINDS:
        original_amount = left.original_gross_amount or right.original_gross_amount
        if original_amount is not None and abs(left.gross_amount) < original_amount:
            return "partial_refund"
        return "refund_or_reversal"
    if left.gross_amount != right.gross_amount and left.net_amount == right.net_amount:
        return "fee_aware"
    if "reference" in candidate.evidence:
        return "exact_reference"
    if candidate.amount_difference > 0:
        return "amount_tolerance"
    if candidate.date_difference_days > 0:
        return "date_window"
    return "exact_amount"


def _deduplicate(
    records: Sequence[CanonicalRecord], side: str
) -> tuple[list[CanonicalRecord], list[Discrepancy]]:
    unique: dict[str, CanonicalRecord] = {}
    discrepancies: list[Discrepancy] = []
    for record in records:
        key = record.idempotency_key
        if key in unique:
            discrepancies.append(
                Discrepancy(
                    classification="duplicate_input",
                    side=side,
                    record_ids=(key,),
                    details={"duplicate_of": key},
                )
            )
            continue
        unique[key] = record
    return list(unique.values()), discrepancies


def _unmatched_classification(
    record: CanonicalRecord,
    others: Iterable[CanonicalRecord],
    config: ReconciliationConfig,
) -> str:
    compatible = [
        other
        for other in others
        if other.source == record.source
        and other.account_id == record.account_id
        and _compatible_kinds(record.kind, other.kind)
    ]
    for other in compatible:
        amount_matches = abs(record.net_amount - other.net_amount) <= config.amount_tolerance
        date_matches = (
            abs((record.occurred_at.date() - other.occurred_at.date()).days) <= config.date_window_days
        )
        if amount_matches and date_matches and record.currency != other.currency:
            return "currency_mismatch"
    same_currency = [other for other in compatible if other.currency == record.currency]
    if any(abs(record.net_amount - other.net_amount) <= config.amount_tolerance for other in same_currency):
        return "date_out_of_window"
    if any(
        abs((record.occurred_at.date() - other.occurred_at.date()).days) <= config.date_window_days
        for other in same_currency
    ):
        return "amount_mismatch"
    if record.kind in REFUND_KINDS:
        return "unmatched_refund"
    return "missing_counterpart"


def _fingerprint(
    left_records: Sequence[CanonicalRecord],
    right_records: Sequence[CanonicalRecord],
    config: ReconciliationConfig,
) -> str:
    def serialized(record: CanonicalRecord) -> dict[str, str]:
        return {
            "key": record.idempotency_key,
            "kind": record.kind,
            "gross": str(record.gross_amount),
            "fee": str(record.fee_amount),
            "net": str(record.net_amount),
            "currency": record.currency,
            "occurred_at": record.occurred_at.isoformat(),
            "reference": record.reference or "",
        }

    payload = {
        "left": sorted((serialized(record) for record in left_records), key=lambda value: value["key"]),
        "right": sorted((serialized(record) for record in right_records), key=lambda value: value["key"]),
        "config": {key: str(value) for key, value in asdict(config).items()},
    }
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def reconcile(
    left_records: Sequence[CanonicalRecord],
    right_records: Sequence[CanonicalRecord],
    config: ReconciliationConfig | None = None,
) -> ReconciliationResult:
    """Reconcile one-to-one candidates first, then bounded many-to-one splits."""

    config = config or ReconciliationConfig()
    left, discrepancies = _deduplicate(left_records, "left")
    right, right_duplicates = _deduplicate(right_records, "right")
    discrepancies.extend(right_duplicates)
    left_by_id = {record.idempotency_key: record for record in left}
    right_by_id = {record.idempotency_key: record for record in right}

    candidates_by_left: dict[str, list[Candidate]] = defaultdict(list)
    for left_record in left:
        for right_record in right:
            candidate = score_candidate(left_record, right_record, config)
            if candidate is not None and candidate.score >= config.minimum_score:
                candidates_by_left[left_record.idempotency_key].append(candidate)
        candidates_by_left[left_record.idempotency_key].sort(
            key=lambda candidate: (-candidate.score, candidate.right_id)
        )

    ambiguous_left: set[str] = set()
    ambiguous_right: set[str] = set()
    proposals: list[Candidate] = []
    for left_id, candidates in candidates_by_left.items():
        if len(candidates) > 1 and candidates[0].score - candidates[1].score <= config.ambiguity_delta:
            ambiguous_left.add(left_id)
            ambiguous_right.update(candidate.right_id for candidate in candidates[:2])
            discrepancies.append(
                Discrepancy(
                    classification="ambiguous_candidates",
                    side="left",
                    record_ids=(left_id, *(candidate.right_id for candidate in candidates[:2])),
                    details={"top_scores": [str(candidate.score) for candidate in candidates[:2]]},
                )
            )
        elif candidates:
            proposals.append(candidates[0])

    proposals_by_right: dict[str, list[Candidate]] = defaultdict(list)
    for proposal in proposals:
        proposals_by_right[proposal.right_id].append(proposal)
    rejected_by_right: set[str] = set()
    for right_id, candidates in proposals_by_right.items():
        candidates.sort(key=lambda candidate: (-candidate.score, candidate.left_id))
        if len(candidates) > 1 and candidates[0].score - candidates[1].score <= config.ambiguity_delta:
            conflicting_left = tuple(candidate.left_id for candidate in candidates[:2])
            ambiguous_left.update(conflicting_left)
            ambiguous_right.add(right_id)
            rejected_by_right.update(conflicting_left)
            discrepancies.append(
                Discrepancy(
                    classification="ambiguous_candidates",
                    side="right",
                    record_ids=(*conflicting_left, right_id),
                    details={"top_scores": [str(candidate.score) for candidate in candidates[:2]]},
                )
            )

    matches: list[Match] = []
    matched_left: set[str] = set()
    matched_right: set[str] = set()
    for candidate in sorted(proposals, key=lambda value: (-value.score, value.left_id, value.right_id)):
        if candidate.left_id in ambiguous_left or candidate.left_id in rejected_by_right:
            continue
        if candidate.left_id in matched_left or candidate.right_id in matched_right:
            continue
        left_record = left_by_id[candidate.left_id]
        right_record = right_by_id[candidate.right_id]
        matches.append(
            Match(
                left_ids=(candidate.left_id,),
                right_ids=(candidate.right_id,),
                score=candidate.score,
                classification=_match_classification(left_record, right_record, candidate),
                amount_difference=candidate.amount_difference,
                date_difference_days=candidate.date_difference_days,
                evidence=candidate.evidence,
            )
        )
        matched_left.add(candidate.left_id)
        matched_right.add(candidate.right_id)

    split_ambiguous_left: set[str] = set()
    split_ambiguous_right: set[str] = set()
    for right_record in sorted(right, key=lambda record: record.idempotency_key):
        right_id = right_record.idempotency_key
        if right_id in matched_right or right_id in ambiguous_right:
            continue
        available_left = [
            record
            for record in left
            if record.idempotency_key not in matched_left
            and record.idempotency_key not in ambiguous_left
            and record.source == right_record.source
            and record.account_id == right_record.account_id
            and record.currency == right_record.currency
            and _compatible_kinds(record.kind, right_record.kind)
            and abs((record.occurred_at.date() - right_record.occurred_at.date()).days)
            <= config.date_window_days
        ]
        valid_groups: list[tuple[CanonicalRecord, ...]] = []
        for size in range(2, min(config.max_split_size, len(available_left)) + 1):
            for group in combinations(available_left, size):
                if (
                    abs(sum((record.net_amount for record in group), Decimal("0")) - right_record.net_amount)
                    <= config.amount_tolerance
                ):
                    valid_groups.append(group)
        if len(valid_groups) == 1:
            group = valid_groups[0]
            left_ids = tuple(record.idempotency_key for record in group)
            matches.append(
                Match(
                    left_ids=left_ids,
                    right_ids=(right_id,),
                    score=Decimal("0.8500"),
                    classification="split_payment",
                    amount_difference=abs(
                        sum((record.net_amount for record in group), Decimal("0")) - right_record.net_amount
                    ),
                    date_difference_days=max(
                        abs((record.occurred_at.date() - right_record.occurred_at.date()).days)
                        for record in group
                    ),
                    evidence=("currency", "bounded_group_sum", "date_window"),
                )
            )
            matched_left.update(left_ids)
            matched_right.add(right_id)
        elif len(valid_groups) > 1:
            involved_left = tuple(
                sorted({record.idempotency_key for group in valid_groups for record in group})
            )
            split_ambiguous_left.update(involved_left)
            split_ambiguous_right.add(right_id)
            discrepancies.append(
                Discrepancy(
                    classification="ambiguous_split",
                    side="right",
                    record_ids=(*involved_left, right_id),
                    details={"candidate_group_count": len(valid_groups)},
                )
            )

    ambiguous_left.update(split_ambiguous_left)
    ambiguous_right.update(split_ambiguous_right)
    for left_record in left:
        left_id = left_record.idempotency_key
        if left_id in matched_left or left_id in ambiguous_left:
            continue
        discrepancies.append(
            Discrepancy(
                classification=_unmatched_classification(left_record, right, config),
                side="left",
                record_ids=(left_id,),
            )
        )
    for right_record in right:
        right_id = right_record.idempotency_key
        if right_id in matched_right or right_id in ambiguous_right:
            continue
        discrepancies.append(
            Discrepancy(
                classification=_unmatched_classification(right_record, left, config),
                side="right",
                record_ids=(right_id,),
            )
        )

    duplicate_count = sum(item.classification == "duplicate_input" for item in discrepancies)
    stats = {
        "left_input_records": len(left_records),
        "right_input_records": len(right_records),
        "left_unique_records": len(left),
        "right_unique_records": len(right),
        "match_groups": len(matches),
        "matched_left_records": len(matched_left),
        "matched_right_records": len(matched_right),
        "discrepancies": len(discrepancies),
        "duplicate_records": duplicate_count,
    }
    return ReconciliationResult(
        matches=tuple(sorted(matches, key=lambda match: (match.left_ids, match.right_ids))),
        discrepancies=tuple(
            sorted(discrepancies, key=lambda item: (item.classification, item.side, item.record_ids))
        ),
        input_fingerprint=_fingerprint(left, right, config),
        stats=stats,
    )
