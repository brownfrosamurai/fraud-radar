from collections.abc import Callable
from datetime import datetime, timezone
from uuid import uuid4

from api.schemas import ScoreRequest
from streaming.publisher import Publisher


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
