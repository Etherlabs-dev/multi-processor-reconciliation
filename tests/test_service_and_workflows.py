from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from reconciliation.service import app
from reconciliation.workflow_validation import validate_directory, validate_workflow

ROOT = Path(__file__).resolve().parents[1]


def test_service_normalizes_and_reconciles() -> None:
    client = TestClient(app)
    normalized = client.post(
        "/normalize",
        json={
            "processor": "ach",
            "account_id": "bank",
            "records": [
                {
                    "external_id": "bank-1",
                    "amount": "97.10",
                    "currency": "USD",
                    "date": "2026-01-11",
                }
            ],
        },
    )
    assert normalized.status_code == 200
    assert normalized.json()["records"][0]["net_amount"] == "97.10"

    payload = {
        "left": [
            {
                "external_id": "charge-1",
                "processor": "ach",
                "processor_account_id": "bank",
                "net_amount": "97.10",
                "gross_amount": "100.00",
                "fee_amount": "2.90",
                "currency": "USD",
                "occurred_at": "2026-01-10",
            }
        ],
        "right": normalized.json()["records"],
    }
    response = client.post("/reconcile", json=payload)
    assert response.status_code == 200
    assert response.json()["stats"]["match_groups"] == 1


def test_service_rejects_malformed_input() -> None:
    response = TestClient(app).post(
        "/normalize", json={"processor": "ach", "account_id": "x", "records": [{}]}
    )
    assert response.status_code == 422


def test_all_eight_workflows_are_structurally_valid_and_secret_free() -> None:
    assert len(validate_directory(ROOT / "n8n" / "workflows")) == 8


def test_workflows_do_not_duplicate_deterministic_money_math() -> None:
    forbidden_fragments = ("float(", "gross -", "confidence', 1.0) * 100")
    for path in (ROOT / "n8n" / "workflows").glob("*.json"):
        workflow = json.loads(path.read_text())
        code = "\n".join(str(node.get("parameters", {}).get("code", "")) for node in workflow["nodes"])
        assert not any(fragment in code for fragment in forbidden_fragments), path.name


def test_workflow_validator_detects_embedded_secret(tmp_path: Path) -> None:
    path = tmp_path / "unsafe.json"
    path.write_text('{"name":"x","nodes":[],"connections":{},"apiKey":"live-secret"}')
    errors = validate_workflow(path)
    assert any("embedded secret" in error for error in errors)


def test_workflow_validator_detects_bearer_value(tmp_path: Path) -> None:
    path = tmp_path / "unsafe.json"
    path.write_text('{"name":"x","nodes":[],"connections":{},"header":"Bearer abcdefghijklmnopqrstuvwxyz"}')
    assert any("embedded secret" in error for error in validate_workflow(path))
