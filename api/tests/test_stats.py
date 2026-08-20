from api.tests.conftest import sample_request


def test_stats_after_score(client) -> None:
    scored = client.post("/score", json=sample_request(amount=20.0))
    assert scored.status_code == 200
    assert "scoring_ms" not in scored.json()
    res = client.get("/stats")
    assert res.status_code == 200
    body = res.json()
    assert body["processed"] >= 1
    assert body["flagged"] >= 0
    assert body["throughput_tx_per_s"] >= 0
    assert body["latency_p50_ms"] is not None
    assert body["latency_p95_ms"] is not None
