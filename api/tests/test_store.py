from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
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


from api.store import stats_from_rows


def test_stats_counts_and_throughput_window() -> None:
    store = InMemoryStore()
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    old = _row().model_copy(update={"created_at": now - timedelta(seconds=6), "decision": "ALLOW"})
    fresh_allow = _row().model_copy(update={"created_at": now - timedelta(seconds=1), "decision": "ALLOW"})
    flagged = _row().model_copy(
        update={"created_at": now - timedelta(seconds=1), "decision": "BLOCK", "model_score": 0.95}
    )
    store.put_many([old, fresh_allow, flagged])
    snap = store.stats(now=now)
    assert snap.processed == 3
    assert snap.flagged == 1
    assert snap.throughput_tx_per_s == pytest.approx(2 / 5)


def test_stats_latency_last_200_skips_nulls() -> None:
    store = InMemoryStore()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    store.put(_row().model_copy(update={"scoring_ms": None}))
    store.put(_row().model_copy(update={"scoring_ms": 10}))
    store.put(_row().model_copy(update={"scoring_ms": 30}))
    snap = store.stats(now=now)
    assert snap.latency_p50_ms == 20
    assert snap.latency_p95_ms is not None


def test_list_alerts_excludes_allow_and_paginates() -> None:
    store = InMemoryStore()
    allow = _row().model_copy(update={"decision": "ALLOW"})
    review = _row().model_copy(update={"decision": "REVIEW", "amount": 10.0, "model_score": 0.5})
    block = _row().model_copy(update={"decision": "BLOCK", "amount": 90.0, "model_score": 0.95})
    store.put_many([allow, review, block])
    page = store.list_alerts(filter="all", sort="amount", dir="desc", offset=0, limit=1)
    assert page.total == 2
    assert page.limit == 1
    assert page.items[0].id == block.id
    page2 = store.list_alerts(filter="all", sort="amount", dir="desc", offset=1, limit=1)
    assert page2.items[0].id == review.id


def test_list_alerts_filter_review_only() -> None:
    store = InMemoryStore()
    store.put_many([
        _row().model_copy(update={"decision": "REVIEW"}),
        _row().model_copy(update={"decision": "BLOCK"}),
    ])
    page = store.list_alerts(filter="review", sort="created_at", dir="desc", offset=0, limit=10)
    assert page.total == 1
    assert page.items[0].decision == "REVIEW"


def test_postgres_list_alerts_does_not_load_all_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    create_tables(engine)
    store = PostgresStore(engine)
    allow = _row().model_copy(update={"decision": "ALLOW", "amount": 1.0})
    review = _row().model_copy(update={"decision": "REVIEW", "amount": 10.0, "model_score": 0.5})
    block = _row().model_copy(update={"decision": "BLOCK", "amount": 90.0, "model_score": 0.95})
    store.put_many([allow, review, block])
    def boom_alerts() -> list:
        raise AssertionError("list_alerts must not hydrate the full table")

    monkeypatch.setattr(store, "_load_all", boom_alerts)
    page = store.list_alerts(filter="all", sort="amount", dir="desc", offset=0, limit=1)
    assert page.total == 2
    assert page.limit == 1
    assert page.items[0].id == block.id
    assert page.items[0].decision == "BLOCK"
    review_only = store.list_alerts(filter="review", sort="created_at", dir="desc", offset=0, limit=10)
    assert review_only.total == 1
    assert review_only.items[0].id == review.id


def test_postgres_stats_does_not_load_all_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    create_tables(engine)
    store = PostgresStore(engine)
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    store.put_many(
        [
            _row().model_copy(
                update={"created_at": now - timedelta(seconds=6), "decision": "ALLOW", "scoring_ms": 4}
            ),
            _row().model_copy(
                update={
                    "created_at": now - timedelta(seconds=1),
                    "decision": "BLOCK",
                    "model_score": 0.95,
                    "scoring_ms": 8,
                }
            ),
        ]
    )
    def boom_stats() -> list:
        raise AssertionError("stats must not hydrate the full table")

    monkeypatch.setattr(store, "_load_all", boom_stats)
    snap = store.stats(now=now)
    assert snap.processed == 2
    assert snap.flagged == 1
    assert snap.throughput_tx_per_s == pytest.approx(1 / 5)
    assert snap.latency_p50_ms is not None


def test_scoring_ms_excluded_from_json() -> None:
    row = _row().model_copy(update={"scoring_ms": 42})
    dumped = row.model_dump(mode="json")
    assert "scoring_ms" not in dumped
    assert row.scoring_ms == 42
