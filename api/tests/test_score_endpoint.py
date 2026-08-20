from api.scoring import score
from api.tests.conftest import sample_request


def test_score_canned_percentiles() -> None:
    from api.schemas import ScoreRequest

    low = ScoreRequest.model_validate(sample_request(amount=20.0))
    mid = ScoreRequest.model_validate(sample_request(amount=150.0))
    high = ScoreRequest.model_validate(sample_request(amount=600.0))
    assert score(low) == 0.12
    assert score(mid) == 0.55
    assert score(high) == 0.93


def test_post_score_low_amount_allows(client) -> None:
    payload = sample_request(amount=20.0)
    res = client.post("/score", json=payload)
    assert res.status_code == 200
    body = res.json()
    assert body["id"] == payload["transaction_id"]
    assert body["model_score"] == 0.12
    assert body["decision"] == "ALLOW"
    assert body["model_name"] == "isolation_forest"
    assert "explanation" not in body


def test_post_score_mid_amount_reviews(client) -> None:
    res = client.post("/score", json=sample_request(amount=150.0))
    assert res.status_code == 200
    assert res.json()["decision"] == "REVIEW"
    assert res.json()["model_score"] == 0.55


def test_post_score_high_amount_blocks(client) -> None:
    res = client.post("/score", json=sample_request(amount=600.0))
    assert res.status_code == 200
    assert res.json()["decision"] == "BLOCK"
    assert res.json()["model_score"] == 0.93


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
