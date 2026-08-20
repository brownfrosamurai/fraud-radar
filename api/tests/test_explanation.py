from uuid import UUID, uuid4

from api.schemas import ScoredTransaction
from api.tests.conftest import sample_request
from ml.features import FEATURE_COLUMNS


def test_explanation_404_when_unscored(client) -> None:
    res = client.get(f"/transactions/{uuid4()}/explanation")
    assert res.status_code == 404
    assert res.json()["detail"] == "transaction not found"


def test_explanation_after_score_is_permutation_top5(client) -> None:
    scored = client.post("/score", json=sample_request(amount=600.0)).json()
    res = client.get(f"/transactions/{scored['id']}/explanation")
    assert res.status_code == 200
    body = res.json()
    assert body["transaction_id"] == scored["id"]
    items = body["explanation"]
    assert len(items) == 5
    names = [item["feature"] for item in items]
    assert names != ["Amount", "V14", "V10", "V4", "V12"] or [
        item["contribution"] for item in items
    ] != [0.42, 0.21, 0.15, 0.11, 0.08]
    assert set(names) <= set(FEATURE_COLUMNS)
    contribs = [item["contribution"] for item in items]
    assert contribs == sorted(contribs, reverse=True)
    assert all(c >= 0 for c in contribs)


def test_explanation_differs_for_different_rows(client) -> None:
    low = client.post("/score", json=sample_request(amount=20.0)).json()
    high_payload = sample_request(amount=900.0)
    high_payload["features"]["V14"] = 8.0
    high = client.post("/score", json=high_payload).json()
    a = client.get(f"/transactions/{low['id']}/explanation").json()["explanation"]
    b = client.get(f"/transactions/{high['id']}/explanation").json()["explanation"]
    assert a != b


def test_explanation_ae_without_weights_is_501(client, store) -> None:
    scored = client.post("/score", json=sample_request(amount=20.0)).json()
    row = store.get(UUID(scored["id"]))
    assert row is not None
    store.put(
        ScoredTransaction(
            id=row.id,
            occurred_at=row.occurred_at,
            amount=row.amount,
            model_score=row.model_score,
            decision=row.decision,
            model_name="autoencoder",
            features=row.features,
            created_at=row.created_at,
        )
    )
    res = client.get(f"/transactions/{scored['id']}/explanation")
    assert res.status_code == 501
