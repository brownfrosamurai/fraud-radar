from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from api.burst import (
    BURST_PAYLOAD_PATH,
    BURST_SIZE,
    BURST_WINDOW_MS,
    COOLDOWN_SECONDS,
    load_burst_rows,
)
from api.main import create_app
from api.serve import ConstScorer
from api.tests.conftest import sample_request


def test_burst_forwards_to_producer_and_does_not_write_store(
    store, clock, producer
) -> None:
    client = TestClient(
        create_app(store=store, clock=clock, scorer=ConstScorer(0.93), producer=producer)
    )
    res = client.post("/demo/burst")
    assert res.status_code == 200
    assert res.json() == {
        "accepted": True,
        "size": BURST_SIZE,
        "window_ms": BURST_WINDOW_MS,
        "cooldown_seconds": COOLDOWN_SECONDS,
    }
    assert producer.calls == 1
    assert store.list_recent(limit=50) == []


def test_burst_cooldown_is_429_and_does_not_call_producer(
    burst_client, producer
) -> None:
    first = burst_client.post("/demo/burst")
    assert first.status_code == 200
    second = burst_client.post("/demo/burst")
    assert second.status_code == 429
    body = second.json()
    assert body["accepted"] is False
    assert 1 <= body["cooldown_seconds"] <= 30
    assert producer.calls == 1


def test_burst_still_cooling_down_just_before_30_seconds(
    burst_client, clock, producer
) -> None:
    burst_client.post("/demo/burst")
    clock.t = clock.t + timedelta(seconds=29.9)
    res = burst_client.post("/demo/burst")
    assert res.status_code == 429
    assert res.json()["cooldown_seconds"] == 1
    assert producer.calls == 1


def test_burst_accepted_at_exactly_30_seconds(burst_client, clock, producer) -> None:
    burst_client.post("/demo/burst")
    clock.t = clock.t + timedelta(seconds=30)
    res = burst_client.post("/demo/burst")
    assert res.status_code == 200
    assert producer.calls == 2


def test_burst_producer_down_is_503_and_skips_cooldown(
    store, clock, producer
) -> None:
    producer.fail = True
    client = TestClient(
        create_app(store=store, clock=clock, scorer=ConstScorer(0.93), producer=producer)
    )
    res = client.post("/demo/burst")
    assert res.status_code == 503
    assert res.json() == {
        "accepted": False,
        "size": BURST_SIZE,
        "window_ms": BURST_WINDOW_MS,
        "cooldown_seconds": 0,
    }
    producer.fail = False
    retry = client.post("/demo/burst")
    assert retry.status_code == 200
    assert producer.calls == 1


def test_load_burst_rows_rejects_wrong_length(tmp_path) -> None:
    path = tmp_path / "burst.json"
    path.write_text("[]")
    with pytest.raises(ValueError, match="exactly 50"):
        load_burst_rows(path)


def test_load_burst_rows_committed_payload_is_burst_size() -> None:
    rows = load_burst_rows(BURST_PAYLOAD_PATH)
    assert len(rows) == BURST_SIZE


def test_create_app_fails_when_artifacts_missing(store, clock, producer, monkeypatch) -> None:
    def boom() -> None:
        raise FileNotFoundError("artifacts missing")

    monkeypatch.setattr("api.main.load_bundle", boom)
    with pytest.raises(FileNotFoundError, match="artifacts missing"):
        create_app(store=store, clock=clock, producer=producer)


def test_injected_scorer_is_not_replaced_by_load_bundle(
    store, clock, producer, monkeypatch
) -> None:
    injected = ConstScorer(0.93)

    def boom() -> None:
        raise AssertionError("load_bundle must not run when a scorer is injected")

    monkeypatch.setattr("api.main.load_bundle", boom)
    app = create_app(store=store, clock=clock, scorer=injected, producer=producer)
    client = TestClient(app)
    assert client.post("/demo/burst").status_code == 200
    assert client.post("/score", json=sample_request()).status_code == 200
    assert app.state.scorer is injected


def test_burst_openapi_documents_200_429_503(client) -> None:
    spec = client.get("/openapi.json").json()
    responses = spec["paths"]["/demo/burst"]["post"]["responses"]
    assert "200" in responses
    assert "429" in responses
    assert "503" in responses
