from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from reconciliation.models import CanonicalRecord, RecordKind


@pytest.fixture
def record_factory():
    def make(
        external_id: str,
        amount: str,
        *,
        source: str = "ledger",
        account_id: str = "acct",
        kind: RecordKind = RecordKind.PAYMENT,
        fee: str = "0",
        gross: str | None = None,
        currency: str = "USD",
        day: int = 10,
        reference: str | None = None,
        original_gross: str | None = None,
    ) -> CanonicalRecord:
        net = Decimal(amount)
        return CanonicalRecord(
            source=source,
            account_id=account_id,
            external_id=external_id,
            kind=kind,
            gross_amount=Decimal(gross if gross is not None else amount),
            fee_amount=Decimal(fee),
            net_amount=net,
            currency=currency,
            occurred_at=datetime(2026, 1, day, 12, tzinfo=UTC),
            reference=reference,
            original_gross_amount=Decimal(original_gross) if original_gross else None,
        )

    return make
