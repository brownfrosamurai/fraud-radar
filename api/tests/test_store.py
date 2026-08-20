from datetime import datetime, timezone
from uuid import uuid4

from api.schemas import Features, ScoredTransaction
from api.store import MAX_ROWS, InMemoryStore


def _row() -> ScoredTransaction:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    features = Features.model_validate({"Time": 0.0, **{f"V{i}": 0.0 for i in range(1, 29)}})
    return ScoredTransaction(
        id=uuid4(),
        occurred_at=now,
        amount=20.0,
        model_score=0.12,
        decision="ALLOW",
        model_name="isolation_forest",
        features=features,
        created_at=now,
    )


def test_store_evicts_oldest_beyond_cap() -> None:
    store = InMemoryStore()
    first = _row()
    store.put(first)
    last = first
    for _ in range(MAX_ROWS):
        last = _row()
        store.put(last)
    assert store.get(first.id) is None
    assert store.get(last.id) is not None
    recent = store.list_recent(limit=50)
    assert len(recent) == 50
    assert first.id not in {row.id for row in recent}


def test_store_burst_of_50_fits() -> None:
    store = InMemoryStore()
    for _ in range(50):
        store.put(_row())
    assert len(store.list_recent(limit=50)) == 50
