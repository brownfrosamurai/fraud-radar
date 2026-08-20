from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from api.burst import BURST_SIZE, BURST_WINDOW_MS, COOLDOWN_SECONDS
from api.main import create_app
from api.schemas import Features, ScoreRequest
from api.serve import ConstScorer
from api.tests.conftest import sample_features


def _payload_row(v14: float) -> ScoreRequest:
    feats = sample_features(V14=v14)
    return ScoreRequest(
        transaction_id=uuid4(),
        occurred_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        amount=1.0,
        features=Features.model_validate(feats),
    )


def test_burst_injects_50_payload_rows_not_amount_stubs(store, clock) -> None:
    rows = [_payload_row(v14=-3.0) for _ in range(50)]
    client = TestClient(
        create_app(store=store, clock=clock, scorer=ConstScorer(0.93), burst_rows=rows)
    )
    res = client.post("/demo/burst")
    assert res.status_code == 200
    assert res.json() == {
        "accepted": True,
        "size": BURST_SIZE,
        "window_ms": BURST_WINDOW_MS,
        "cooldown_seconds": COOLDOWN_SECONDS,
    }
    stored = store.list_recent(limit=50)
    assert len(stored) == 50
    assert all(row.decision == "BLOCK" for row in stored)
    assert all(row.amount == 1.0 for row in stored)
    assert all(row.features.V14 == -3.0 for row in stored)
    assert all(row.model_name == "isolation_forest" for row in stored)


def test_burst_cooldown_is_429_not_queued(burst_client, clock) -> None:
    first = burst_client.post("/demo/burst")
    assert first.status_code == 200
    second = burst_client.post("/demo/burst")
    assert second.status_code == 429
    body = second.json()
    assert body["accepted"] is False
    assert body["size"] == 50
    assert 1 <= body["cooldown_seconds"] <= 30
    rows = burst_client.get("/transactions", params={"limit": 50}).json()
    assert len(rows) == 50


def test_burst_accepted_after_cooldown(burst_client, clock) -> None:
    burst_client.post("/demo/burst")
    clock.t = clock.t + timedelta(seconds=31)
    res = burst_client.post("/demo/burst")
    assert res.status_code == 200
    assert res.json()["accepted"] is True
    rows = burst_client.get("/transactions", params={"limit": 50}).json()
    assert len(rows) == 50


def _schema_ref(response: dict) -> str:
    schema = response["content"]["application/json"]["schema"]
    return schema.get("$ref", schema.get("anyOf", [{}])[0].get("$ref", ""))


def test_burst_openapi_documents_200_and_429(client) -> None:
    spec = client.get("/openapi.json").json()
    responses = spec["paths"]["/demo/burst"]["post"]["responses"]
    assert "BurstResponse" in _schema_ref(responses["200"])
    assert "BurstResponse" in _schema_ref(responses["429"])
    assert "BurstResponse" in spec["components"]["schemas"]
