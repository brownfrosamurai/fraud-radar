from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from api.burst import BURST_SIZE, BURST_WINDOW_MS, COOLDOWN_SECONDS
from api.main import create_app
from api.schemas import Features, ScoreRequest
from api.serve import ConstScorer
from api.tests.conftest import sample_features, sample_request, tiny_if_bundle


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


def test_score_then_burst_share_lazy_loaded_scorer(store, clock, burst_rows, monkeypatch) -> None:
    calls = {"n": 0}

    def fake_load_bundle():
        calls["n"] += 1
        return tiny_if_bundle()

    monkeypatch.setattr("api.main.load_bundle", fake_load_bundle)
    app = create_app(store=store, clock=clock, burst_rows=burst_rows)
    client = TestClient(app)
    assert app.state.scorer is None
    assert app.state.burst._scorer is None

    score_res = client.post("/score", json=sample_request())
    assert score_res.status_code == 200
    assert calls["n"] == 1
    assert app.state.burst._scorer is app.state.scorer

    burst_res = client.post("/demo/burst")
    assert burst_res.status_code == 200
    assert calls["n"] == 1
    assert app.state.burst._scorer is app.state.scorer


def test_burst_then_score_share_lazy_loaded_scorer(store, clock, burst_rows, monkeypatch) -> None:
    calls = {"n": 0}

    def fake_load_bundle():
        calls["n"] += 1
        return tiny_if_bundle()

    monkeypatch.setattr("api.main.load_bundle", fake_load_bundle)
    app = create_app(store=store, clock=clock, burst_rows=burst_rows)
    client = TestClient(app)

    burst_res = client.post("/demo/burst")
    assert burst_res.status_code == 200
    assert calls["n"] == 1
    assert app.state.burst._scorer is app.state.scorer
    assert app.state.scorer is not None

    score_res = client.post("/score", json=sample_request())
    assert score_res.status_code == 200
    assert calls["n"] == 1
    assert app.state.burst._scorer is app.state.scorer


def test_injected_scorer_is_not_replaced_by_load_bundle(store, clock, burst_rows, monkeypatch) -> None:
    injected = ConstScorer(0.93)

    def boom() -> None:
        raise AssertionError("load_bundle must not run when a scorer is injected")

    monkeypatch.setattr("api.main.load_bundle", boom)
    app = create_app(store=store, clock=clock, scorer=injected, burst_rows=burst_rows)
    client = TestClient(app)
    assert client.post("/demo/burst").status_code == 200
    assert client.post("/score", json=sample_request()).status_code == 200
    assert app.state.scorer is injected
    assert app.state.burst._scorer is injected


def test_burst_openapi_documents_200_and_429(client) -> None:
    spec = client.get("/openapi.json").json()
    responses = spec["paths"]["/demo/burst"]["post"]["responses"]
    assert "BurstResponse" in _schema_ref(responses["200"])
    assert "BurstResponse" in _schema_ref(responses["429"])
    assert "BurstResponse" in spec["components"]["schemas"]
