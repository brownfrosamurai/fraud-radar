from uuid import uuid4

from api.tests.conftest import sample_request


def test_explanation_404_when_unscored(client) -> None:
    res = client.get(f"/transactions/{uuid4()}/explanation")
    assert res.status_code == 404
    assert res.json()["detail"] == "transaction not found"


def test_explanation_canned_features_after_score(client) -> None:
    scored = client.post("/score", json=sample_request(amount=600.0)).json()
    res = client.get(f"/transactions/{scored['id']}/explanation")
    assert res.status_code == 200
    body = res.json()
    assert body["transaction_id"] == scored["id"]
    names = [item["feature"] for item in body["explanation"]]
    assert names == ["Amount", "V14", "V10", "V4", "V12"]
    assert [item["contribution"] for item in body["explanation"]] == [
        0.42,
        0.21,
        0.15,
        0.11,
        0.08,
    ]
