from datetime import datetime, timezone
from uuid import uuid4

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import QuantileTransformer, StandardScaler

from api.main import create_app
from api.serve import BundleScorer, ConstScorer, ModelBundle
from api.store import InMemoryStore


class FakeProducer:
    def __init__(self) -> None:
        self.calls = 0
        self.fail = False

    def trigger_burst(self) -> None:
        from api.burst import ProducerUnavailable

        if self.fail:
            raise ProducerUnavailable()
        self.calls += 1


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


def tiny_if_bundle() -> ModelBundle:
    rng = np.random.default_rng(0)
    X = rng.normal(size=(60, 30))
    scaler = StandardScaler().fit(X)
    Xs = scaler.transform(X)
    model = IsolationForest(n_estimators=20, random_state=42).fit(Xs)
    raw = -model.score_samples(Xs)
    cdf = QuantileTransformer(
        output_distribution="uniform", n_quantiles=min(60, 1000), random_state=42
    ).fit(raw.reshape(-1, 1))
    return ModelBundle(scaler=scaler, isolation_forest=model, if_cdf=cdf)


@pytest.fixture
def store() -> InMemoryStore:
    return InMemoryStore()


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(datetime(2026, 1, 1, tzinfo=timezone.utc))


@pytest.fixture
def scorer() -> BundleScorer:
    return BundleScorer(tiny_if_bundle())


@pytest.fixture
def producer() -> FakeProducer:
    return FakeProducer()


@pytest.fixture
def client(
    store: InMemoryStore,
    clock: FrozenClock,
    scorer: BundleScorer,
    producer: FakeProducer,
) -> TestClient:
    return TestClient(
        create_app(store=store, clock=clock, scorer=scorer, producer=producer)
    )


@pytest.fixture
def burst_client(
    store: InMemoryStore, clock: FrozenClock, producer: FakeProducer
) -> TestClient:
    return TestClient(
        create_app(store=store, clock=clock, scorer=ConstScorer(0.93), producer=producer)
    )
