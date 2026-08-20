import logging
from datetime import datetime
from typing import Protocol

from api.schemas import ScoreRequest, ScoredTransaction
from api.scoring import decide
from api.serve import Scorer

logger = logging.getLogger(__name__)


def parse_message(raw: bytes) -> ScoreRequest | None:
    try:
        return ScoreRequest.model_validate_json(raw)
    except Exception:
        logger.warning("skipping malformed kafka message")
        return None


def score_request(req: ScoreRequest, scorer: Scorer, now: datetime) -> ScoredTransaction:
    model_score = scorer.score(req, model="isolation_forest")
    return ScoredTransaction(
        id=req.transaction_id,
        occurred_at=req.occurred_at,
        amount=req.amount,
        model_score=model_score,
        decision=decide(model_score, req.amount),
        model_name="isolation_forest",
        features=req.features,
        created_at=now,
    )


class Notifier(Protocol):
    def notify(self, rows: list[ScoredTransaction]) -> None: ...


class HttpNotifier:
    def __init__(self, url: str) -> None:
        self._url = url

    def notify(self, rows: list[ScoredTransaction]) -> None:
        import httpx

        try:
            httpx.post(
                self._url,
                json=[row.model_dump(mode="json") for row in rows],
                timeout=2.0,
            )
        except Exception:
            logger.exception("commit notify failed")
