from __future__ import annotations

from decimal import Decimal

from reconciliation.matching import reconcile, score_candidate
from reconciliation.models import ReconciliationConfig, RecordKind


def test_exact_reference_match(record_factory) -> None:
    left = record_factory("charge", "97.10", reference="order-1")
    right = record_factory("payout", "97.10", reference="order-1", day=11)
    result = reconcile([left], [right])
    assert result.matches[0].classification == "exact_reference"
    assert result.matches[0].score == Decimal("0.9833")


def test_date_window_boundary_is_allowed_but_later_date_is_not(record_factory) -> None:
    left = record_factory("a", "20.00", day=10)
    allowed = record_factory("b", "20.00", day=13)
    rejected = record_factory("c", "20.00", day=14)
    assert score_candidate(left, allowed) is not None
    assert score_candidate(left, rejected) is None


def test_fee_aware_comparison_uses_net(record_factory) -> None:
    left = record_factory("charge", "97.10", gross="100.00", fee="2.90")
    right = record_factory("payout", "97.10", gross="97.10")
    result = reconcile([left], [right])
    assert result.matches[0].classification == "fee_aware"


def test_full_and_partial_refunds_are_classified(record_factory) -> None:
    full_left = record_factory("r1", "-100", kind=RecordKind.REFUND, gross="-100")
    full_right = record_factory("r2", "-100", kind=RecordKind.REFUND, gross="-100")
    partial_left = record_factory("r3", "-25", kind=RecordKind.REFUND, gross="-25", original_gross="100")
    partial_right = record_factory("r4", "-25", kind=RecordKind.REFUND, gross="-25")
    result = reconcile([full_left, partial_left], [full_right, partial_right])
    assert {match.classification for match in result.matches} == {"refund_or_reversal", "partial_refund"}


def test_split_payment_requires_a_unique_bounded_group(record_factory) -> None:
    left = [record_factory("part-a", "40"), record_factory("part-b", "60")]
    right = [record_factory("settlement", "100")]
    result = reconcile(left, right)
    assert result.matches[0].classification == "split_payment"
    assert set(result.matches[0].left_ids) == {item.idempotency_key for item in left}


def test_close_candidates_are_left_unresolved(record_factory) -> None:
    left = [record_factory("charge", "10")]
    right = [
        record_factory("candidate-a", "10"),
        record_factory("candidate-b", "10"),
    ]
    result = reconcile(left, right)
    assert not result.matches
    assert any(item.classification == "ambiguous_candidates" for item in result.discrepancies)


def test_missing_currency_mismatch_and_duplicates_are_explicit(record_factory) -> None:
    duplicate = record_factory("same", "15")
    eur = record_factory("eur", "15", currency="EUR")
    missing = record_factory("missing", "99", day=20)
    result = reconcile([duplicate, duplicate], [eur, missing])
    classifications = {item.classification for item in result.discrepancies}
    assert {"duplicate_input", "currency_mismatch", "missing_counterpart"} <= classifications
    assert result.stats["duplicate_records"] == 1


def test_result_and_fingerprint_are_order_independent(record_factory) -> None:
    left = [record_factory("a", "10"), record_factory("b", "20")]
    right = [
        record_factory("x", "10", reference="a"),
        record_factory("y", "20", reference="b"),
    ]
    first = reconcile(left, right)
    second = reconcile(list(reversed(left)), list(reversed(right)))
    assert first == second


def test_invalid_config_is_rejected() -> None:
    try:
        ReconciliationConfig(amount_tolerance=Decimal("-0.01"))
    except ValueError as exc:
        assert "amount_tolerance" in str(exc)
    else:
        raise AssertionError("negative tolerance was accepted")


def test_cross_account_candidate_is_never_eligible(record_factory) -> None:
    left = record_factory("left", "100", account_id="merchant-a")
    right = record_factory("right", "100", account_id="merchant-b")
    assert score_candidate(left, right) is None
