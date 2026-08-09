"""Replay-safe checkpoint and accounting-posting primitives."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Any


class CursorConflict(ValueError):
    """Raised when a worker tries to advance a stale checkpoint."""


class IdempotencyConflict(ValueError):
    """Raised when an idempotency key is reused for different content."""


@dataclass(frozen=True, slots=True)
class BatchResult:
    accepted_event_ids: tuple[str, ...]
    duplicate_event_ids: tuple[str, ...]
    cursor: str | None
    advanced: bool


class IngestionCheckpointStore:
    """In-memory reference implementation of atomic cursor/event semantics.

    Production adapters should enforce the same behavior in a database transaction.
    """

    def __init__(self) -> None:
        self._cursors: dict[str, str | None] = {}
        self._processed: set[tuple[str, str]] = set()

    def current_cursor(self, source: str) -> str | None:
        return self._cursors.get(source)

    def apply_batch(
        self,
        *,
        source: str,
        expected_cursor: str | None,
        next_cursor: str | None,
        event_ids: list[str] | tuple[str, ...],
    ) -> BatchResult:
        current = self.current_cursor(source)
        if expected_cursor != current:
            raise CursorConflict(
                f"stale cursor for {source}: expected {expected_cursor!r}, current {current!r}"
            )

        accepted: list[str] = []
        duplicates: list[str] = []
        seen_in_batch: set[str] = set()
        for raw_event_id in event_ids:
            event_id = str(raw_event_id).strip()
            if not event_id:
                raise ValueError("event IDs must be non-empty")
            key = (source, event_id)
            if event_id in seen_in_batch or key in self._processed:
                duplicates.append(event_id)
            else:
                accepted.append(event_id)
                seen_in_batch.add(event_id)

        self._processed.update((source, event_id) for event_id in accepted)
        advanced = next_cursor != current
        self._cursors[source] = next_cursor
        return BatchResult(tuple(accepted), tuple(duplicates), next_cursor, advanced)


@dataclass(frozen=True, slots=True)
class PostingDecision:
    should_post: bool
    replay: bool
    payload_hash: str


class AccountingSyncLedger:
    """Reject changed payloads and suppress identical accounting replays."""

    def __init__(self) -> None:
        self._payload_hashes: dict[str, str] = {}

    def reserve(self, idempotency_key: str, payload: dict[str, Any]) -> PostingDecision:
        key = idempotency_key.strip()
        if not key:
            raise ValueError("idempotency key is required")
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
        payload_hash = sha256(encoded).hexdigest()
        previous = self._payload_hashes.get(key)
        if previous is None:
            self._payload_hashes[key] = payload_hash
            return PostingDecision(True, False, payload_hash)
        if previous != payload_hash:
            raise IdempotencyConflict(f"idempotency key {key!r} was reused with a different payload")
        return PostingDecision(False, True, payload_hash)
