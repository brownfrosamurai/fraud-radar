from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.store import InMemoryStore


class FrozenClock:
    def __init__(self, t: datetime) -> None:
        self.t = t

    def __call__(self) -> datetime:
        return self.t


def sample_features(**overrides: float) -> dict[str, float]:
    data = {"Time": 0.0}
    for i in range(1, 29):
        data[f"V{i}"] = 0.0
    data.update(overrides)
    return data


def sample_request(amount: float = 20.0) -> dict:
    return {
        "transaction_id": str(uuid4()),
        "occurred_at": datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
        "amount": amount,
        "features": sample_features(),
    }


@pytest.fixture
def store() -> InMemoryStore:
    return InMemoryStore()


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(datetime(2026, 1, 1, tzinfo=timezone.utc))


@pytest.fixture
def client(store: InMemoryStore, clock: FrozenClock) -> TestClient:
    return TestClient(create_app(store=store, clock=clock))
