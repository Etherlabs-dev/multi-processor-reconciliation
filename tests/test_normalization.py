from __future__ import annotations

from datetime import UTC
from decimal import Decimal

import pytest

from reconciliation.models import RecordKind
from reconciliation.normalization import (
    normalize_currency,
    normalize_money,
    normalize_record,
    normalize_timestamp,
)


def test_stripe_minor_units_and_fee_are_exact() -> None:
    record = normalize_record(
        "stripe",
        {
            "id": "ch_1",
            "type": "charge",
            "amount": 10001,
            "fee": 291,
            "currency": "usd",
            "created": 1_767_225_600,
        },
        "acct_1",
    )
    assert record.gross_amount == Decimal("100.01")
    assert record.fee_amount == Decimal("2.91")
    assert record.net_amount == Decimal("97.10")
    assert record.currency == "USD"
    assert record.occurred_at.tzinfo == UTC


def test_paypal_partial_refund_has_negative_sign_and_origin() -> None:
    record = normalize_record(
        "paypal",
        {
            "transaction_info": {
                "transaction_id": "refund_1",
                "transaction_event_code": "partial_refund",
                "transaction_amount": {"value": "25.00", "currency_code": "USD"},
                "fee_amount": {"value": "0.00"},
                "transaction_initiation_date": "2026-01-10T10:00:00Z",
                "paypal_reference_id": "sale_1",
                "original_gross_amount": "100.00",
            }
        },
        "acct_2",
    )
    assert record.kind is RecordKind.REFUND
    assert record.net_amount == Decimal("-25.00")
    assert record.original_external_id == "sale_1"
    assert record.original_gross_amount == Decimal("100.00")


@pytest.mark.parametrize("value", [None, True, "NaN", "Infinity", "bad"])
def test_malformed_money_is_rejected(value: object) -> None:
    with pytest.raises(ValueError):
        normalize_money(value)


@pytest.mark.parametrize("value", [None, "US", "USDD", "12$"])
def test_malformed_currency_is_rejected(value: object) -> None:
    with pytest.raises(ValueError):
        normalize_currency(value)


def test_naive_timestamp_is_explicitly_interpreted_as_utc() -> None:
    assert normalize_timestamp("2026-01-01T03:04:05").tzinfo == UTC


def test_missing_identifier_is_rejected() -> None:
    with pytest.raises(ValueError, match="external_id"):
        normalize_record(
            "ach",
            {"amount": 10, "currency": "USD", "date": "2026-01-01"},
            "ach_1",
        )
