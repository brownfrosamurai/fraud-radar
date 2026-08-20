import json
import math
import threading
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
from uuid import uuid4

import httpx

from api.schemas import BurstResponse, Features, ScoreRequest

BURST_SIZE = 50
BURST_WINDOW_MS = 2000
COOLDOWN_SECONDS = 30
BURST_PAYLOAD_PATH = Path("ml/artifacts/burst_payload.json")


class CooldownActive(Exception):
    def __init__(self, remaining: int) -> None:
        self.remaining = remaining


class ProducerClient(Protocol):
    def trigger_burst(self) -> None: ...


class ProducerUnavailable(Exception):
    pass


class HttpProducerClient:
    def __init__(self, base_url: str, timeout: float = 2.0) -> None:
        self._url = base_url.rstrip("/") + "/burst"
        self._timeout = timeout

    def trigger_burst(self) -> None:
        try:
            res = httpx.post(self._url, timeout=self._timeout)
        except httpx.RequestError as exc:
            raise ProducerUnavailable from exc
        if not 200 <= res.status_code < 300:
            raise ProducerUnavailable


def load_burst_rows(path: Path) -> list[ScoreRequest]:
    raw = json.loads(path.read_text())
    if not isinstance(raw, list) or len(raw) != BURST_SIZE:
        n = len(raw) if isinstance(raw, list) else type(raw).__name__
        raise ValueError(f"burst payload must contain exactly {BURST_SIZE} rows, got {n}")
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


class BurstController:
    def __init__(
        self,
        clock: Callable[[], datetime],
        producer: ProducerClient,
    ) -> None:
        self._clock = clock
        self._producer = producer
        self._last_burst_at: datetime | None = None
        self._lock = threading.Lock()

    def trigger(self) -> BurstResponse:
        with self._lock:
            now = self._clock()
            if self._last_burst_at is not None:
                elapsed = (now - self._last_burst_at).total_seconds()
                if elapsed < COOLDOWN_SECONDS:
                    remaining = math.ceil(COOLDOWN_SECONDS - elapsed)
                    raise CooldownActive(remaining)
            self._producer.trigger_burst()
            self._last_burst_at = now
            return BurstResponse(
                accepted=True,
                size=BURST_SIZE,
                window_ms=BURST_WINDOW_MS,
                cooldown_seconds=COOLDOWN_SECONDS,
            )
