"""Deterministic synthetic benchmark for matcher verification."""

from __future__ import annotations

import argparse
import json
import platform
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from time import perf_counter_ns

from reconciliation.matching import reconcile
from reconciliation.models import CanonicalRecord, ReconciliationConfig, RecordKind
from reconciliation.serialization import to_jsonable

SEED = 20260809


def _record(
    source: str,
    external_id: str,
    net: str,
    *,
    day: int = 10,
    kind: RecordKind = RecordKind.PAYMENT,
    gross: str | None = None,
    fee: str = "0",
    currency: str = "USD",
    reference: str | None = None,
    original_gross: str | None = None,
) -> CanonicalRecord:
    return CanonicalRecord(
        source=source,
        account_id="synthetic",
        external_id=external_id,
        kind=kind,
        gross_amount=Decimal(gross if gross is not None else net),
        fee_amount=Decimal(fee),
        net_amount=Decimal(net),
        currency=currency,
        occurred_at=datetime(2026, 1, day, 12, tzinfo=UTC),
        reference=reference,
        original_gross_amount=Decimal(original_gross) if original_gross else None,
    )


def synthetic_case() -> tuple[
    list[CanonicalRecord], list[CanonicalRecord], set[tuple[frozenset[str], frozenset[str]]]
]:
    left = [
        _record("synthetic", "exact", "10.11", reference="order-exact"),
        _record("synthetic", "date-window", "20.22"),
        _record("synthetic", "fee-aware", "27.09", gross="30.00", fee="2.91"),
        _record("synthetic", "refund", "-40.40", kind=RecordKind.REFUND),
        _record(
            "synthetic",
            "partial-refund",
            "-12.12",
            kind=RecordKind.REFUND,
            original_gross="50.00",
        ),
        _record("synthetic", "split-a", "31.00"),
        _record("synthetic", "split-b", "32.00"),
        _record("synthetic", "ambiguous", "70.70"),
        _record("synthetic", "missing", "80.80", day=20),
        _record("synthetic", "duplicate", "90.90"),
        _record("synthetic", "duplicate", "90.90"),
        _record("synthetic", "currency", "99.99"),
    ]
    right = [
        _record("synthetic", "exact-bank", "10.11", day=11, reference="order-exact"),
        _record("synthetic", "date-bank", "20.22", day=13),
        _record("synthetic", "fee-bank", "27.09"),
        _record("synthetic", "refund-bank", "-40.40", kind=RecordKind.REFUND),
        _record("synthetic", "partial-bank", "-12.12", kind=RecordKind.REFUND),
        _record("synthetic", "split-bank", "63.00"),
        _record("synthetic", "ambiguous-a", "70.70"),
        _record("synthetic", "ambiguous-b", "70.70"),
        _record("synthetic", "currency-bank", "99.99", currency="EUR"),
    ]
    pairs = [
        (("exact",), ("exact-bank",)),
        (("date-window",), ("date-bank",)),
        (("fee-aware",), ("fee-bank",)),
        (("refund",), ("refund-bank",)),
        (("partial-refund",), ("partial-bank",)),
        (("split-a", "split-b"), ("split-bank",)),
    ]
    expected = {
        (
            frozenset(f"synthetic:synthetic:{value}" for value in left_ids),
            frozenset(f"synthetic:synthetic:{value}" for value in right_ids),
        )
        for left_ids, right_ids in pairs
    }
    return left, right, expected


def run_benchmark() -> dict[str, object]:
    left, right, expected = synthetic_case()
    config = ReconciliationConfig()
    start = perf_counter_ns()
    result = reconcile(left, right, config)
    runtime_ms = (perf_counter_ns() - start) / 1_000_000
    actual = {(frozenset(match.left_ids), frozenset(match.right_ids)) for match in result.matches}
    correct = len(actual & expected)
    false = len(actual - expected)
    unresolved = (
        result.stats["left_unique_records"]
        + result.stats["right_unique_records"]
        - result.stats["matched_left_records"]
        - result.stats["matched_right_records"]
    )
    return {
        "evidence_label": "synthetic",
        "seed": SEED,
        "expected_matches": len(expected),
        "correct_matches": correct,
        "false_matches": false,
        "unresolved_records": unresolved,
        "duplicate_records": result.stats["duplicate_records"],
        "runtime_ms": round(runtime_ms, 4),
        "input_fingerprint": result.input_fingerprint,
        "config": to_jsonable(config),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run_benchmark()
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{rendered}\n")
    print(rendered)


if __name__ == "__main__":
    main()
