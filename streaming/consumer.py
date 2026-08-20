import logging
import time
from collections.abc import Iterable
from datetime import datetime, timezone
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
    started = time.perf_counter()
    model_score = scorer.score(req, model="isolation_forest")
    decision = decide(model_score, req.amount)
    scoring_ms = int((time.perf_counter() - started) * 1000)
    return ScoredTransaction(
        id=req.transaction_id,
        occurred_at=req.occurred_at,
        amount=req.amount,
        model_score=model_score,
        decision=decision,
        model_name="isolation_forest",
        features=req.features,
        created_at=now,
        scoring_ms=scoring_ms,
    )


class Notifier(Protocol):
    def notify(self, rows: list[ScoredTransaction]) -> None: ...


class HttpNotifier:
    def __init__(self, url: str, secret: str | None = None) -> None:
        self._url = url
        self._secret = secret

    def notify(self, rows: list[ScoredTransaction]) -> None:
        import httpx

        try:
            response = httpx.post(
                self._url,
                json=[row.model_dump(mode="json") for row in rows],
                headers={"X-Internal-Secret": self._secret} if self._secret else None,
                timeout=2.0,
            )
            response.raise_for_status()
        except Exception:
            logger.exception("commit notify failed")


def run_consumer(
    bootstrap: str,
    store: TransactionStore,
    scorer: Scorer,
    notify: Notifier,
    topic: str = "transactions",
    group_id: str = "fraud-radar-scorer",
    messages: Iterable[bytes] | None = None,
) -> None:
    from streaming.batch import BatchWriter

    writer = BatchWriter(
        store=store,
        notify=notify.notify,
        clock=lambda: datetime.now(timezone.utc),
    )

    def process(raw: bytes) -> None:
        req = parse_message(raw)
        if req is None:
            return
        writer.add(score_request(req, scorer, datetime.now(timezone.utc)))

    if messages is not None:
        for raw in messages:
            process(raw)
        writer.flush_pending()
        return

    from kafka import KafkaConsumer

    consumer = KafkaConsumer(
        topic,
        bootstrap_servers=bootstrap,
        group_id=group_id,
        auto_offset_reset="latest",
        value_deserializer=lambda v: v,
    )
    while True:
        records = consumer.poll(timeout_ms=100)
        if not records:
            writer.flush_if_needed()
            continue
        for batch in records.values():
            for msg in batch:
                process(msg.value)


def main() -> None:
    import os

    from api.db import create_engine_from_url
    from api.postgres_store import PostgresStore
    from api.serve import BundleScorer, load_bundle

    store = PostgresStore(create_engine_from_url(os.environ["DATABASE_URL"]))
    scorer = BundleScorer(load_bundle())
    notifier = HttpNotifier(
        os.environ.get("NOTIFY_URL", "http://api:8000/internal/scored"),
        secret=os.environ.get("INTERNAL_API_SECRET"),
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
