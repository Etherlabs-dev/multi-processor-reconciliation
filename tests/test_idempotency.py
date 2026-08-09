from __future__ import annotations

import pytest

from reconciliation.idempotency import (
    AccountingSyncLedger,
    CursorConflict,
    IdempotencyConflict,
    IngestionCheckpointStore,
)


def test_checkpoint_advances_after_batch_and_duplicate_events_are_suppressed() -> None:
    store = IngestionCheckpointStore()
    first = store.apply_batch(
        source="stripe:acct", expected_cursor=None, next_cursor="page-1", event_ids=["e1", "e1", "e2"]
    )
    assert first.accepted_event_ids == ("e1", "e2")
    assert first.duplicate_event_ids == ("e1",)
    replay = store.apply_batch(
        source="stripe:acct", expected_cursor="page-1", next_cursor="page-1", event_ids=["e1", "e2"]
    )
    assert not replay.accepted_event_ids
    assert replay.duplicate_event_ids == ("e1", "e2")
    assert not replay.advanced


def test_stale_worker_cannot_overwrite_cursor() -> None:
    store = IngestionCheckpointStore()
    store.apply_batch(source="paypal", expected_cursor=None, next_cursor="1", event_ids=["e1"])
    with pytest.raises(CursorConflict):
        store.apply_batch(source="paypal", expected_cursor=None, next_cursor="2", event_ids=["e2"])
    assert store.current_cursor("paypal") == "1"


def test_invalid_batch_does_not_advance_checkpoint() -> None:
    store = IngestionCheckpointStore()
    with pytest.raises(ValueError):
        store.apply_batch(source="ach", expected_cursor=None, next_cursor="1", event_ids=[""])
    assert store.current_cursor("ach") is None


def test_accounting_replay_is_suppressed_and_mutation_conflicts() -> None:
    ledger = AccountingSyncLedger()
    payload = {"debits": "100.00", "credits": "100.00", "currency": "USD"}
    assert ledger.reserve("payout:1", payload).should_post
    replay = ledger.reserve("payout:1", dict(reversed(list(payload.items()))))
    assert replay.replay and not replay.should_post
    with pytest.raises(IdempotencyConflict):
        ledger.reserve("payout:1", {**payload, "debits": "99.00"})
