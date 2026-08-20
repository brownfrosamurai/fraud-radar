import logging
from datetime import datetime
from typing import Protocol

from api.schemas import ScoreRequest, ScoredTransaction
from api.scoring import decide
from api.serve import Scorer
from api.store import TransactionStore

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


def run_consumer(
    bootstrap: str,
    store: TransactionStore,
    scorer: Scorer,
    notify: Notifier,
    topic: str = "transactions",
    group_id: str = "fraud-radar-scorer",
) -> None:
    from datetime import timezone

    from kafka import KafkaConsumer

    from streaming.batch import BatchWriter

    consumer = KafkaConsumer(
        topic,
        bootstrap_servers=bootstrap,
        group_id=group_id,
        auto_offset_reset="latest",
        value_deserializer=lambda v: v,
    )
    writer = BatchWriter(
        store=store,
        notify=notify.notify,
        clock=lambda: datetime.now(timezone.utc),
    )
    for msg in consumer:
        req = parse_message(msg.value)
        if req is None:
            continue
        writer.add(score_request(req, scorer, datetime.now(timezone.utc)))
        writer.flush_if_needed()


def main() -> None:
    import os

    from api.db import create_engine_from_url
    from api.postgres_store import PostgresStore
    from api.serve import BundleScorer, load_bundle

    store = PostgresStore(create_engine_from_url(os.environ["DATABASE_URL"]))
    scorer = BundleScorer(load_bundle())
    notifier = HttpNotifier(
        os.environ.get("NOTIFY_URL", "http://api:8000/internal/scored")
    )
    run_consumer(
        bootstrap=os.environ.get("KAFKA_BOOTSTRAP", "redpanda:9092"),
        store=store,
        scorer=scorer,
        notify=notifier,
        topic=os.environ.get("KAFKA_TOPIC", "transactions"),
        group_id=os.environ.get("KAFKA_GROUP", "fraud-radar-scorer"),
    )


if __name__ == "__main__":
    main()
