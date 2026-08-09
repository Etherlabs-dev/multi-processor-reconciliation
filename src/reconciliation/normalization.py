"""Processor-specific normalization with exact decimal and timestamp handling."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from reconciliation.models import CanonicalRecord, RecordKind

CENT = Decimal("0.01")
REFUND_KINDS = {RecordKind.REFUND, RecordKind.REVERSAL}


def normalize_money(value: Any, *, minor_units: bool = False) -> Decimal:
    if value is None or isinstance(value, bool):
        raise ValueError("money value is required and must be numeric")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"invalid money value: {value!r}") from exc
    if not amount.is_finite():
        raise ValueError("money value must be finite")
    if minor_units:
        amount /= Decimal(100)
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def normalize_currency(value: Any) -> str:
    currency = str(value or "").strip().upper()
    if len(currency) != 3 or not currency.isalpha() or not currency.isascii():
        raise ValueError(f"currency must be a three-letter ASCII code: {value!r}")
    return currency


def normalize_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, datetime.min.time(), tzinfo=UTC)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        parsed = datetime.fromtimestamp(value, tz=UTC)
    elif isinstance(value, str) and value.strip():
        text = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValueError(f"invalid timestamp: {value!r}") from exc
    else:
        raise ValueError("occurred_at is required")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _record_kind(value: Any) -> RecordKind:
    text = str(value or "payment").strip().lower()
    if "partial_refund" in text or "refund" in text:
        return RecordKind.REFUND
    if "reversal" in text or "chargeback" in text:
        return RecordKind.REVERSAL
    if "payout" in text or "settlement" in text:
        return RecordKind.PAYOUT
    if "fee" in text:
        return RecordKind.FEE
    if "charge" in text:
        return RecordKind.CHARGE
    return RecordKind.PAYMENT


def _canonical(
    *,
    source: str,
    account_id: str | int,
    external_id: Any,
    kind: RecordKind,
    gross_amount: Any,
    fee_amount: Any,
    net_amount: Any | None,
    currency: Any,
    occurred_at: Any,
    reference: Any = None,
    original_external_id: Any = None,
    original_gross_amount: Any = None,
    minor_units: bool = False,
    metadata: Mapping[str, Any] | None = None,
) -> CanonicalRecord:
    identifier = str(external_id or "").strip()
    if not identifier:
        raise ValueError("external_id is required")
    normalized_account_id = str(account_id or "").strip()
    if not normalized_account_id:
        raise ValueError("account_id is required")
    source_name = source.strip().lower()
    if not source_name:
        raise ValueError("source is required")

    gross = normalize_money(gross_amount, minor_units=minor_units)
    fee = abs(normalize_money(fee_amount or 0, minor_units=minor_units))
    if kind in REFUND_KINDS:
        gross = -abs(gross)
    elif kind == RecordKind.FEE:
        gross = Decimal("0.00")

    computed_net = gross - fee
    net = computed_net if net_amount is None else normalize_money(net_amount, minor_units=minor_units)
    if kind in REFUND_KINDS and net > 0:
        net = -net
    if kind == RecordKind.FEE:
        net = -fee

    original_amount = (
        None
        if original_gross_amount in (None, "")
        else abs(normalize_money(original_gross_amount, minor_units=minor_units))
    )
    return CanonicalRecord(
        source=source_name,
        account_id=normalized_account_id,
        external_id=identifier,
        kind=kind,
        gross_amount=gross,
        fee_amount=fee,
        net_amount=net,
        currency=normalize_currency(currency),
        occurred_at=normalize_timestamp(occurred_at),
        reference=str(reference).strip() if reference not in (None, "") else None,
        original_external_id=(
            str(original_external_id).strip() if original_external_id not in (None, "") else None
        ),
        original_gross_amount=original_amount,
        metadata=dict(metadata or {}),
    )


def normalize_record(processor: str, payload: Mapping[str, Any], account_id: str | int) -> CanonicalRecord:
    """Normalize Stripe, PayPal, Square, ACH, or canonical records."""

    source = processor.strip().lower()
    if source == "stripe":
        return _canonical(
            source=source,
            account_id=account_id,
            external_id=payload.get("id"),
            kind=_record_kind(payload.get("type")),
            gross_amount=payload.get("amount", 0),
            fee_amount=payload.get("fee", 0),
            net_amount=payload.get("net"),
            currency=payload.get("currency"),
            occurred_at=payload.get("created"),
            reference=payload.get("source") or payload.get("reference"),
            original_external_id=payload.get("original_transaction"),
            original_gross_amount=payload.get("original_amount"),
            minor_units=True,
            metadata=payload,
        )
    if source == "paypal":
        detail = payload.get("transaction_info", payload)
        amount = detail.get("transaction_amount", {})
        fee = detail.get("fee_amount", {})
        return _canonical(
            source=source,
            account_id=account_id,
            external_id=detail.get("transaction_id") or detail.get("id"),
            kind=_record_kind(detail.get("transaction_event_code") or detail.get("type")),
            gross_amount=amount.get("value", detail.get("gross_amount", 0)),
            fee_amount=fee.get("value", detail.get("fee_amount", 0)),
            net_amount=detail.get("net_amount"),
            currency=amount.get("currency_code", detail.get("currency")),
            occurred_at=detail.get("transaction_initiation_date") or detail.get("occurred_at"),
            reference=detail.get("paypal_reference_id") or detail.get("reference"),
            original_external_id=detail.get("paypal_reference_id"),
            original_gross_amount=detail.get("original_gross_amount"),
            metadata=payload,
        )
    if source == "square":
        amount = payload.get("amount_money", {})
        fee = payload.get("total_fee_money", {})
        return _canonical(
            source=source,
            account_id=account_id,
            external_id=payload.get("id"),
            kind=_record_kind(payload.get("type") or payload.get("status")),
            gross_amount=amount.get("amount", payload.get("gross_amount", 0)),
            fee_amount=fee.get("amount", payload.get("fee_amount", 0)),
            net_amount=payload.get("net_amount"),
            currency=amount.get("currency", payload.get("currency")),
            occurred_at=payload.get("created_at") or payload.get("occurred_at"),
            reference=payload.get("order_id") or payload.get("reference"),
            original_external_id=payload.get("payment_id"),
            original_gross_amount=payload.get("original_gross_amount"),
            minor_units="amount" in amount,
            metadata=payload,
        )
    if source in {"ach", "canonical"}:
        return _canonical(
            source=str(payload.get("processor") or payload.get("source") or source),
            account_id=payload.get("processor_account_id") or payload.get("account_id") or account_id,
            external_id=payload.get("external_id") or payload.get("transaction_id") or payload.get("id"),
            kind=_record_kind(payload.get("type") or payload.get("kind")),
            gross_amount=payload.get("gross_amount", payload.get("amount", 0)),
            fee_amount=payload.get("fee_amount", payload.get("fee", 0)),
            net_amount=payload.get("net_amount"),
            currency=payload.get("currency"),
            occurred_at=payload.get("occurred_at") or payload.get("date") or payload.get("payout_date"),
            reference=payload.get("reference") or payload.get("customer_ref"),
            original_external_id=payload.get("original_external_id"),
            original_gross_amount=payload.get("original_gross_amount"),
            metadata=payload,
        )
    raise ValueError(f"unsupported processor: {processor!r}")


def normalize_records(
    processor: str,
    records: Iterable[Mapping[str, Any]],
    account_id: str | int,
) -> tuple[CanonicalRecord, ...]:
    return tuple(normalize_record(processor, record, account_id) for record in records)
