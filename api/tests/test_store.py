from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import create_engine

from api.db import create_tables
from api.postgres_store import PostgresStore
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


def test_in_memory_put_many_then_list_recent() -> None:
    store = InMemoryStore()
    rows = [_row() for _ in range(3)]
    store.put_many(rows)
    recent = store.list_recent(limit=50)
    assert [r.id for r in recent] == list(reversed([r.id for r in rows]))


def test_postgres_store_roundtrip_sqlite() -> None:
    engine = create_engine("sqlite:///:memory:")
    create_tables(engine)
    store = PostgresStore(engine)
    row = _row()
    store.put(row)
    got = store.get(row.id)
    assert got is not None
    assert got.id == row.id
    assert got.amount == row.amount
    assert got.decision == row.decision
    assert got.features.V14 == row.features.V14


def test_postgres_store_put_many_and_list_cap_50() -> None:
    engine = create_engine("sqlite:///:memory:")
    create_tables(engine)
    store = PostgresStore(engine)
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = []
    for i in range(51):
        row = _row()
        row = row.model_copy(update={"created_at": base + timedelta(seconds=i)})
        rows.append(row)
    store.put_many(rows)
    recent = store.list_recent(limit=50)
    assert len(recent) == 50
    assert recent[0].id == rows[-1].id
    assert rows[0].id not in {r.id for r in recent}


def test_postgres_store_get_missing_is_none() -> None:
    engine = create_engine("sqlite:///:memory:")
    create_tables(engine)
    store = PostgresStore(engine)
    assert store.get(_row().id) is None
