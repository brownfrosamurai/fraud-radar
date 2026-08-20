import json
import threading
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from api.schemas import BurstResponse, Features, ScoreRequest, ScoredTransaction
from api.scoring import decide
from api.serve import Scorer
from api.store import InMemoryStore

BURST_SIZE = 50
BURST_WINDOW_MS = 2000
COOLDOWN_SECONDS = 30
BURST_PAYLOAD_PATH = Path("ml/artifacts/burst_payload.json")


class CooldownActive(Exception):
    def __init__(self, remaining: int) -> None:
        self.remaining = remaining


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
        store: InMemoryStore,
        clock: Callable[[], datetime],
        scorer: Scorer | None,
        burst_rows: list[ScoreRequest] | None = None,
        resolve_scorer: Callable[[], Scorer] | None = None,
    ) -> None:
        self._store = store
        self._clock = clock
        self._scorer = scorer
        self._burst_rows = burst_rows
        self._resolve_scorer = resolve_scorer
        self._last_burst_at: datetime | None = None
        # Cooldown check + inserts must be one critical section vs concurrent POSTs.
        self._lock = threading.Lock()

    def bind_scorer(self, scorer: Scorer) -> None:
        self._scorer = scorer

    def trigger(self) -> BurstResponse:
        with self._lock:
            now = self._clock()
            if self._last_burst_at is not None:
                elapsed = (now - self._last_burst_at).total_seconds()
                remaining = int(COOLDOWN_SECONDS - elapsed)
                if remaining > 0:
                    raise CooldownActive(remaining)
            if self._resolve_scorer is not None:
                self._scorer = self._resolve_scorer()
            rows = self._burst_rows
            if rows is None:
                rows = load_burst_rows(BURST_PAYLOAD_PATH)
                self._burst_rows = rows
            rows = rows[:BURST_SIZE]
            if len(rows) != BURST_SIZE:
                raise ValueError(
                    f"burst requires exactly {BURST_SIZE} rows, got {len(rows)}"
                )
            for src in rows:
                req = ScoreRequest(
                    transaction_id=uuid4(),
                    occurred_at=now,
                    amount=src.amount,
                    features=src.features,
                )
                model_score = self._scorer.score(req, model="isolation_forest")
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
