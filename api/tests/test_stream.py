from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from api.hub import StreamHub
from api.main import create_app
from api.schemas import Features, ScoredTransaction
from api.serve import ConstScorer
from api.store import InMemoryStore
from api.tests.conftest import FakeProducer


def _scored() -> dict:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    feats = {"Time": 0.0, **{f"V{i}": 0.0 for i in range(1, 29)}}
    row = ScoredTransaction(
        id=uuid4(),
        occurred_at=now,
        amount=20.0,
        model_score=0.12,
        decision="ALLOW",
        model_name="isolation_forest",
        features=Features.model_validate(feats),
        created_at=now,
    )
    return row.model_dump(mode="json")


def test_internal_scored_persists_and_broadcasts() -> None:
    store = InMemoryStore()
    hub = StreamHub()
    app = create_app(
        store=store,
        scorer=ConstScorer(0.12),
        producer=FakeProducer(),
        hub=hub,
    )
    payload = _scored()
    with TestClient(app) as client:
        with client.websocket_connect("/stream") as ws:
            res = client.post("/internal/scored", json=[payload])
            assert res.status_code == 200
            msg = ws.receive_json()
            assert msg["id"] == payload["id"]
            assert msg["decision"] == "ALLOW"
    assert store.get(UUID(payload["id"])) is not None


def test_explanation_readable_after_internal_scored() -> None:
    store = InMemoryStore()
    app = create_app(store=store, scorer=ConstScorer(0.12), producer=FakeProducer())
    payload = _scored()
    client = TestClient(app)
    client.post("/internal/scored", json=[payload])
    expl = client.get(f"/transactions/{payload['id']}/explanation")
    assert expl.status_code == 200
    assert expl.json()["explanation"][0]["feature"] == "Amount"
