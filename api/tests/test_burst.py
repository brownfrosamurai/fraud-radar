from datetime import timedelta

from api.burst import BURST_SIZE, BURST_WINDOW_MS, COOLDOWN_SECONDS


def test_burst_injects_50_blocking_rows(client, store) -> None:
    """Slice 1 Task 3: payload still amount stubs; BLOCK guarantee restored in Task 4."""
    res = client.post("/demo/burst")
    assert res.status_code == 200
    body = res.json()
    assert body == {
        "accepted": True,
        "size": BURST_SIZE,
        "window_ms": BURST_WINDOW_MS,
        "cooldown_seconds": COOLDOWN_SECONDS,
    }
    rows = store.list_recent(limit=50)
    assert len(rows) == 50


def test_burst_cooldown_is_429_not_queued(client, clock) -> None:
    first = client.post("/demo/burst")
    assert first.status_code == 200
    second = client.post("/demo/burst")
    assert second.status_code == 429
    body = second.json()
    assert body["accepted"] is False
    assert body["size"] == 50
    assert 1 <= body["cooldown_seconds"] <= 30
    rows = client.get("/transactions", params={"limit": 50}).json()
    assert len(rows) == 50


def test_burst_accepted_after_cooldown(client, clock) -> None:
    client.post("/demo/burst")
    clock.t = clock.t + timedelta(seconds=31)
    res = client.post("/demo/burst")
    assert res.status_code == 200
    assert res.json()["accepted"] is True
    rows = client.get("/transactions", params={"limit": 50}).json()
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

