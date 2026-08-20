from typing import Protocol

from kafka import KafkaProducer

from api.schemas import ScoreRequest

TOPIC = "transactions"


class Publisher(Protocol):
    def publish(self, request: ScoreRequest) -> None: ...


class KafkaPublisher:
    def __init__(self, bootstrap: str, topic: str = TOPIC) -> None:
        self._topic = topic
        self._producer = KafkaProducer(
            bootstrap_servers=bootstrap,
            key_serializer=lambda k: k.encode("utf-8"),
            value_serializer=lambda v: v,
        )

    def publish(self, request: ScoreRequest) -> None:
        payload = request.model_dump_json().encode("utf-8")
        self._producer.send(
            self._topic,
            key=str(request.transaction_id),
            value=payload,
        )
        self._producer.flush()
