from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from api.schemas import Features, ScoreRequest
from streaming.producer import create_producer_app


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


def test_burst_publishes_50_and_has_no_cooldown() -> None:
    rows = [_row() for _ in range(50)]
    pub = RecordingPublisher()
    app = create_producer_app(publish=pub, burst_rows=rows, sleep_fn=lambda _s: None)
    client = TestClient(app)
    first = client.post("/burst")
    assert first.status_code == 200
    assert first.json() == {"accepted": True, "size": 50, "window_ms": 2000}
    second = client.post("/burst")
    assert second.status_code == 200
    assert len(pub.rows) == 100
