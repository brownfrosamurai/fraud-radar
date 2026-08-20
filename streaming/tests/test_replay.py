from datetime import datetime, timezone
from uuid import uuid4

from api.schemas import Features, ScoreRequest
from streaming.replay import fresh_request, replay_loop, spread_publish


def _row() -> ScoreRequest:
    return ScoreRequest(
        transaction_id=uuid4(),
        occurred_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        amount=1.0,
        features=Features.model_validate(
            {"Time": 0.0, **{f"V{i}": 0.0 for i in range(1, 29)}}
        ),
    )


class RecordingPublisher:
    def __init__(self) -> None:
        self.rows: list[ScoreRequest] = []

    def publish(self, request: ScoreRequest) -> None:
        self.rows.append(request)


def test_spread_publish_50_over_2000ms_uses_49_gaps() -> None:
    rows = [_row() for _ in range(50)]
    pub = RecordingPublisher()
    sleeps: list[float] = []
    spread_publish(rows, pub, sleep_fn=sleeps.append, window_ms=2000)
    assert len(pub.rows) == 50
    assert len(sleeps) == 49
    assert abs(sum(sleeps) - 2.0) < 1e-9


def test_fresh_request_mints_new_id() -> None:
    src = _row()
    out = fresh_request(src)
    assert out.transaction_id != src.transaction_id
    assert out.amount == src.amount
    assert out.features.V1 == src.features.V1


def test_replay_loop_rate_and_wrap() -> None:
    rows = [_row(), _row()]
    pub = RecordingPublisher()
    sleeps: list[float] = []
    n = {"i": 0}

    def should_continue() -> bool:
        n["i"] += 1
        return n["i"] <= 4

    replay_loop(
        rows,
        pub,
        sleep_fn=sleeps.append,
        rate_per_sec=10.0,
        should_continue=should_continue,
        clock=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert len(pub.rows) == 4
    assert len(sleeps) == 4
    assert all(abs(s - 0.1) < 1e-9 for s in sleeps)
    assert pub.rows[0].transaction_id != rows[0].transaction_id
    assert pub.rows[2].amount == rows[0].amount
