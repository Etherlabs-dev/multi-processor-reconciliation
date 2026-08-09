"""Immutable financial records and reconciliation result types."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any


class RecordKind(StrEnum):
    CHARGE = "charge"
    PAYMENT = "payment"
    PAYOUT = "payout"
    REFUND = "refund"
    REVERSAL = "reversal"
    FEE = "fee"


@dataclass(frozen=True, slots=True)
class CanonicalRecord:
    source: str
    account_id: str
    external_id: str
    kind: RecordKind
    gross_amount: Decimal
    fee_amount: Decimal
    net_amount: Decimal
    currency: str
    occurred_at: datetime
    reference: str | None = None
    original_external_id: str | None = None
    original_gross_amount: Decimal | None = None
    metadata: dict[str, Any] = field(default_factory=dict, compare=False, hash=False)

    @property
    def idempotency_key(self) -> str:
        return f"{self.source}:{self.account_id}:{self.external_id}"


@dataclass(frozen=True, slots=True)
class ReconciliationConfig:
    amount_tolerance: Decimal = Decimal("0.01")
    date_window_days: int = 3
    minimum_score: Decimal = Decimal("0.70")
    ambiguity_delta: Decimal = Decimal("0.03")
    max_split_size: int = 3

    def __post_init__(self) -> None:
        if self.amount_tolerance < 0:
            raise ValueError("amount_tolerance cannot be negative")
        if self.date_window_days < 0:
            raise ValueError("date_window_days cannot be negative")
        if not Decimal("0") <= self.minimum_score <= Decimal("1"):
            raise ValueError("minimum_score must be between 0 and 1")
        if self.ambiguity_delta < 0:
            raise ValueError("ambiguity_delta cannot be negative")
        if self.max_split_size < 2 or self.max_split_size > 5:
            raise ValueError("max_split_size must be between 2 and 5")


@dataclass(frozen=True, slots=True)
class Candidate:
    left_id: str
    right_id: str
    score: Decimal
    amount_difference: Decimal
    date_difference_days: int
    evidence: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Match:
    left_ids: tuple[str, ...]
    right_ids: tuple[str, ...]
    score: Decimal
    classification: str
    amount_difference: Decimal
    date_difference_days: int
    evidence: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Discrepancy:
    classification: str
    side: str
    record_ids: tuple[str, ...]
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    matches: tuple[Match, ...]
    discrepancies: tuple[Discrepancy, ...]
    input_fingerprint: str
    stats: dict[str, int]
