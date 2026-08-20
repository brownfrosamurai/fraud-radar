import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.serve import ConstScorer
from api.tests.conftest import sample_request


@pytest.fixture
def client(store, clock, producer) -> TestClient:
    # Default IsolationForest fixture scores all-zero features at 0.0 (ALLOW).
    # Alerts omit ALLOW, so these HTTP tests need a scorer that produces flags.
    return TestClient(
        create_app(store=store, clock=clock, scorer=ConstScorer(0.93), producer=producer)
    )


def test_alerts_omits_allow(client) -> None:
    client.post("/score", json=sample_request(amount=20.0))
    client.post("/score", json=sample_request(amount=900.0))
    res = client.get("/alerts", params={"filter": "all", "limit": 10})
    assert res.status_code == 200
    body = res.json()
    assert set(body.keys()) >= {"items", "total", "offset", "limit"}
    assert all(item["decision"] in {"REVIEW", "BLOCK"} for item in body["items"])
    assert "ALLOW" not in {item["decision"] for item in body["items"]}


def test_alerts_bad_sort_is_422(client) -> None:
    res = client.get("/alerts", params={"sort": "nope"})
    assert res.status_code == 422


def test_alerts_sort_amount_desc(client) -> None:
    client.post("/score", json=sample_request(amount=600.0))
    high = client.post("/score", json=sample_request(amount=900.0)).json()
    res = client.get(
        "/alerts",
        params={"sort": "amount", "dir": "desc", "limit": 10},
    )
    items = res.json()["items"]
    if len(items) >= 2:
        assert items[0]["amount"] >= items[1]["amount"]
    assert high["id"] in {item["id"] for item in items} or res.json()["total"] >= 1
