from __future__ import annotations

import os

import psycopg
import pytest

DATABASE_URL = os.getenv("DATABASE_URL")
pytestmark = pytest.mark.postgres


@pytest.fixture
def connection():
    if not DATABASE_URL:
        pytest.skip("DATABASE_URL is not configured")
    with psycopg.connect(DATABASE_URL) as conn:
        yield conn


def test_seed_data_loaded(connection) -> None:
    expected = {
        "processors": 4,
        "processor_accounts": 4,
        "raw_events": 3,
        "ledger_transactions": 3,
        "payouts": 3,
        "recon_runs": 1,
        "recon_matches": 1,
    }
    with connection.cursor() as cursor:
        for table, count in expected.items():
            cursor.execute(f"SELECT count(*) FROM {table}")
            assert cursor.fetchone()[0] == count


def test_raw_event_duplicate_is_rejected(connection) -> None:
    with pytest.raises(psycopg.errors.UniqueViolation), connection.transaction():
        connection.execute(
            """
                INSERT INTO raw_events
                    (id, processor_account_id, processor, event_type, external_id,
                     payload_json, payload_sha256)
                VALUES (99, 1, 'stripe', 'charge.succeeded', 'evt_stripe_1', '{}',
                    '44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a')
            """
        )


def test_accounting_idempotency_and_balanced_journal_constraints(connection) -> None:
    with pytest.raises(psycopg.errors.UniqueViolation), connection.transaction():
        connection.execute(
            """
                INSERT INTO qb_sync_jobs
                    (run_id, idempotency_key, payload_sha256, status, qb_payload_json)
                VALUES (1, 'recon-run:1:stripe',
                    '44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a',
                    'pending', '{}')
                """
        )
    with pytest.raises(psycopg.errors.CheckViolation), connection.transaction():
        connection.execute(
            """
                INSERT INTO qb_postings
                    (sync_job_id, clearing_account, journal_entry_id, debit_total, credit_total,
                     currency, posted_at)
                VALUES (1, 'Stripe Clearing', 'bad-je', 10, 9, 'USD', now())
                """
        )


def test_cursor_compare_and_swap_prevents_stale_replay(connection) -> None:
    with connection.transaction():
        updated = connection.execute(
            """
            UPDATE sync_state
            SET last_cursor = 'cursor2', cursor_version = cursor_version + 1, updated_at = now()
            WHERE processor_account_id = 1 AND cursor_version = 1
            """
        ).rowcount
        stale = connection.execute(
            """
            UPDATE sync_state
            SET last_cursor = 'cursor3', cursor_version = cursor_version + 1, updated_at = now()
            WHERE processor_account_id = 1 AND cursor_version = 1
            """
        ).rowcount
        assert updated == 1
        assert stale == 0
        connection.execute(
            """
            UPDATE sync_state
            SET last_cursor = 'cursor1', cursor_version = 1
            WHERE processor_account_id = 1
            """
        )
