from api.tests.conftest import sample_request


def test_post_score_default_model_is_isolation_forest(client) -> None:
    payload = sample_request(amount=20.0)
    res = client.post("/score", json=payload)
    assert res.status_code == 200
    body = res.json()
    assert body["id"] == payload["transaction_id"]
    assert body["model_name"] == "isolation_forest"
    assert 0.0 <= body["model_score"] <= 1.0
    assert body["decision"] in {"ALLOW", "REVIEW", "BLOCK"}
    assert "explanation" not in body


def test_post_score_invalid_model_is_422(client) -> None:
    res = client.post("/score", params={"model": "nope"}, json=sample_request())
    assert res.status_code == 422


def test_post_score_autoencoder_without_weights_is_501(client) -> None:
    res = client.post("/score", params={"model": "autoencoder"}, json=sample_request())
    assert res.status_code == 501


def test_post_score_rejects_malformed(client) -> None:
    res = client.post("/score", json={"amount": 10})
    assert res.status_code == 422


def test_get_transactions_newest_first(client) -> None:
    first = client.post("/score", json=sample_request(amount=20.0)).json()
    second = client.post("/score", json=sample_request(amount=600.0)).json()
    res = client.get("/transactions", params={"limit": 50})
    assert res.status_code == 200
    rows = res.json()
    assert [row["id"] for row in rows] == [second["id"], first["id"]]


def test_get_transactions_caps_at_50(client) -> None:
    for _ in range(51):
        client.post("/score", json=sample_request(amount=20.0))
    rows = client.get("/transactions", params={"limit": 50}).json()
    assert len(rows) == 50


def test_health(client) -> None:
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}
