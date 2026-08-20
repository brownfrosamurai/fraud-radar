import threading
from collections.abc import Callable
from datetime import datetime
from uuid import uuid4

from api.schemas import BurstResponse, Features, ScoreRequest, ScoredTransaction
from api.scoring import decide, score
from api.serve import Scorer
from api.store import InMemoryStore

BURST_SIZE = 50
BURST_WINDOW_MS = 2000
COOLDOWN_SECONDS = 30


class CooldownActive(Exception):
    def __init__(self, remaining: int) -> None:
        self.remaining = remaining


def _zero_features() -> Features:
    payload = {"Time": 0.0, **{f"V{i}": 0.0 for i in range(1, 29)}}
    return Features.model_validate(payload)


class BurstController:
    def __init__(
        self,
        store: InMemoryStore,
        clock: Callable[[], datetime],
        burst_rows: list[ScoreRequest] | None = None,
        scorer: Scorer | None = None,
    ) -> None:
        self._store = store
        self._clock = clock
        self._burst_rows = burst_rows
        self._scorer = scorer
        self._last_burst_at: datetime | None = None
        # Cooldown check + inserts must be one critical section vs concurrent POSTs.
        self._lock = threading.Lock()

    def trigger(self) -> BurstResponse:
        with self._lock:
            now = self._clock()
            if self._last_burst_at is not None:
                elapsed = (now - self._last_burst_at).total_seconds()
                remaining = int(COOLDOWN_SECONDS - elapsed)
                if remaining > 0:
                    raise CooldownActive(remaining)
            for i in range(BURST_SIZE):
                req = ScoreRequest(
                    transaction_id=uuid4(),
                    occurred_at=now,
                    amount=501.0 + i,
                    features=_zero_features(),
                )
                model_score = score(req, scorer=self._scorer)
                self._store.put(
                    ScoredTransaction(
                        id=req.transaction_id,
                        occurred_at=req.occurred_at,
                        amount=req.amount,
                        model_score=model_score,
                        decision=decide(model_score, req.amount),
                        model_name="isolation_forest",
                        features=req.features,
                        created_at=now,
                    )
                )
            self._last_burst_at = now
            return BurstResponse(
                accepted=True,
                size=BURST_SIZE,
                window_ms=BURST_WINDOW_MS,
                cooldown_seconds=COOLDOWN_SECONDS,
            )
