"""Small HTTP boundary for n8n orchestration."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from reconciliation.matching import reconcile
from reconciliation.models import ReconciliationConfig
from reconciliation.normalization import normalize_record, normalize_records
from reconciliation.serialization import to_jsonable

app = FastAPI(title="Reconciliation Engine", version="0.2.0")


class NormalizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    processor: str
    account_id: str
    records: list[dict[str, Any]]


class ConfigRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount_tolerance: Decimal = Decimal("0.01")
    date_window_days: int = Field(3, ge=0)
    minimum_score: Decimal = Field(Decimal("0.70"), ge=0, le=1)
    ambiguity_delta: Decimal = Field(Decimal("0.03"), ge=0)
    max_split_size: int = Field(3, ge=2, le=5)


class ReconcileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    left: list[dict[str, Any]]
    right: list[dict[str, Any]]
    config: ConfigRequest = ConfigRequest()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/normalize")
def normalize(request: NormalizeRequest) -> dict[str, Any]:
    try:
        records = normalize_records(request.processor, request.records, request.account_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    serialized = to_jsonable(records)
    return {"records": serialized, "record": serialized[0] if len(serialized) == 1 else None}


@app.post("/reconcile")
def reconcile_endpoint(request: ReconcileRequest) -> dict[str, Any]:
    try:
        left = tuple(normalize_record("canonical", item, "left") for item in request.left)
        right = tuple(normalize_record("canonical", item, "right") for item in request.right)
        config = ReconciliationConfig(**request.config.model_dump())
        result = reconcile(left, right, config)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return to_jsonable(result)
