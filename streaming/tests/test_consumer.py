import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx

from api.schemas import Features, ScoreRequest, ScoredTransaction
from api.serve import ConstScorer
from api.store import InMemoryStore
from streaming.batch import BatchWriter
from streaming.consumer import HttpNotifier, parse_message, run_consumer, score_request


def _req() -> ScoreRequest:
    return ScoreRequest(
        transaction_id=uuid4(),
        occurred_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        amount=600.0,
        features=Features.model_validate({"Time": 0.0, **{f"V{i}": 0.0 for i in range(1, 29)}}),
    )


class RecordingNotifier:
    def __init__(self) -> None:
        self.batches: list[list[ScoredTransaction]] = []

    def notify(self, rows: list[ScoredTransaction]) -> None:
        self.batches.append(rows)


class FlakyStore(InMemoryStore):
    def __init__(self, fail_times: int) -> None:
        super().__init__()
        self.fail_times = fail_times
        self.calls = 0

    def put_many(self, rows: list[ScoredTransaction]) -> None:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("db down")
        super().put_many(rows)


def test_parse_message_skips_malformed() -> None:
    assert parse_message(b"not-json") is None
    assert parse_message(b"{}") is None
    good = _req()
    parsed = parse_message(good.model_dump_json().encode())
    assert parsed is not None
    assert parsed.transaction_id == good.transaction_id


def test_score_request_uses_isolation_forest_and_decide() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    row = score_request(_req(), ConstScorer(0.93), now)
    assert row.model_name == "isolation_forest"
    assert row.decision == "BLOCK"
    assert row.model_score == 0.93


def test_run_consumer_skips_malformed_scores_and_flushes_exhausted_source() -> None:
    store = InMemoryStore()
    notifier = RecordingNotifier()
    req = _req()

    run_consumer(
        bootstrap="unused:9092",
        store=store,
        scorer=ConstScorer(0.12),
        notify=notifier,
        messages=[b"not-json", req.model_dump_json().encode()],
    )

    stored = store.get(req.transaction_id)
    assert stored is not None
    assert stored.model_score == 0.12
    assert stored.model_name == "isolation_forest"
    assert len(notifier.batches) == 1
    assert [row.id for row in notifier.batches[0]] == [req.transaction_id]


def test_http_notifier_sends_secret_and_checks_response(
    monkeypatch, caplog
) -> None:
    called: dict[str, object] = {}

    class ErrorResponse:
        def raise_for_status(self) -> None:
            called["checked"] = True
            raise httpx.HTTPStatusError(
                "server error",
                request=httpx.Request("POST", "http://api/internal/scored"),
                response=httpx.Response(500),
            )

    def fake_post(url: str, **kwargs: object) -> ErrorResponse:
        called["url"] = url
        called.update(kwargs)
        return ErrorResponse()

    monkeypatch.setattr(httpx, "post", fake_post)
    caplog.set_level(logging.ERROR)

    HttpNotifier(
        "http://api/internal/scored", secret="test-secret"
    ).notify([score_request(_req(), ConstScorer(0.12), datetime.now(timezone.utc))])

    assert called["headers"] == {"X-Internal-Secret": "test-secret"}
    assert called["checked"] is True
    assert "commit notify failed" in caplog.text


def test_batch_flushes_at_10_rows() -> None:
    store = InMemoryStore()
    notifier = RecordingNotifier()
    clock = {"t": datetime(2026, 1, 1, tzinfo=timezone.utc)}
    writer = BatchWriter(
        store=store,
        notify=notifier.notify,
        clock=lambda: clock["t"],
        max_rows=10,
        max_wait_ms=100,
    )
    for _ in range(10):
        writer.add(score_request(_req(), ConstScorer(0.12), clock["t"]))
    assert len(store.list_recent(limit=50)) == 10
    assert len(notifier.batches) == 1
    assert len(notifier.batches[0]) == 10


def test_batch_flushes_after_100ms() -> None:
    store = InMemoryStore()
    notifier = RecordingNotifier()
    clock = {"t": datetime(2026, 1, 1, tzinfo=timezone.utc)}
    writer = BatchWriter(
        store=store,
        notify=notifier.notify,
        clock=lambda: clock["t"],
        max_rows=10,
        max_wait_ms=100,
    )
    writer.add(score_request(_req(), ConstScorer(0.12), clock["t"]))
    assert notifier.batches == []
    clock["t"] = clock["t"] + timedelta(milliseconds=100)
    writer.flush_if_needed()
    assert len(notifier.batches) == 1


def test_batch_retries_once_then_notifies() -> None:
    store = FlakyStore(fail_times=1)
    notifier = RecordingNotifier()
    clock = {"t": datetime(2026, 1, 1, tzinfo=timezone.utc)}
    writer = BatchWriter(store=store, notify=notifier.notify, clock=lambda: clock["t"])
    for _ in range(10):
        writer.add(score_request(_req(), ConstScorer(0.12), clock["t"]))
    assert store.calls == 2
    assert len(notifier.batches) == 1


def test_batch_drops_after_second_failure_without_notify(caplog) -> None:
    store = FlakyStore(fail_times=99)
    notifier = RecordingNotifier()
    clock = {"t": datetime(2026, 1, 1, tzinfo=timezone.utc)}
    writer = BatchWriter(store=store, notify=notifier.notify, clock=lambda: clock["t"])
    caplog.set_level(logging.ERROR)
    for _ in range(10):
        writer.add(score_request(_req(), ConstScorer(0.12), clock["t"]))
    assert store.calls == 2
    assert notifier.batches == []
    assert store.list_recent(limit=50) == []
