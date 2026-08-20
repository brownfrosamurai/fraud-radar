import json
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from api.schemas import Features, ScoreRequest
from streaming.publisher import Publisher

REPLAY_SIZE = 200


def load_replay_rows(path: Path) -> list[ScoreRequest]:
    raw = json.loads(path.read_text())
    if not isinstance(raw, list) or len(raw) != REPLAY_SIZE:
        n = len(raw) if isinstance(raw, list) else type(raw).__name__
        raise ValueError(f"replay payload must contain exactly {REPLAY_SIZE} rows, got {n}")
    now = datetime.now(timezone.utc)
    return [
        ScoreRequest(
            transaction_id=uuid4(),
            occurred_at=now,
            amount=item["amount"],
            features=Features.model_validate(item["features"]),
        )
        for item in raw
    ]


def fresh_request(
    src: ScoreRequest, occurred_at: datetime | None = None
) -> ScoreRequest:
    return ScoreRequest(
        transaction_id=uuid4(),
        occurred_at=occurred_at or datetime.now(timezone.utc),
        amount=src.amount,
        features=src.features,
    )


def spread_publish(
    rows: list[ScoreRequest],
    publish: Publisher,
    sleep_fn: Callable[[float], None],
    window_ms: int = 2000,
) -> None:
    if not rows:
        return
    gap = (window_ms / 1000.0) / max(len(rows) - 1, 1)
    for i, row in enumerate(rows):
        publish.publish(fresh_request(row))
        if i < len(rows) - 1:
            sleep_fn(gap)


def replay_loop(
    rows: list[ScoreRequest],
    publish: Publisher,
    sleep_fn: Callable[[float], None],
    rate_per_sec: float = 10.0,
    should_continue: Callable[[], bool] = lambda: True,
    clock: Callable[[], datetime] | None = None,
) -> None:
    if not rows:
        raise ValueError("replay payload empty")
    delay = 1.0 / rate_per_sec
    time_fn = clock or (lambda: datetime.now(timezone.utc))
    i = 0
    while should_continue():
        publish.publish(fresh_request(rows[i % len(rows)], occurred_at=time_fn()))
        i += 1
        sleep_fn(delay)
