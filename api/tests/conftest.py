from datetime import datetime, timezone
from uuid import uuid4

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import QuantileTransformer, StandardScaler

from api.main import create_app
from api.serve import BundleScorer, ModelBundle
from api.store import InMemoryStore
from ml.features import FEATURE_COLUMNS, dataframe_to_array


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
    legit = pd.DataFrame(
        [{name: float(rng.normal()) for name in FEATURE_COLUMNS} for _ in range(60)]
    )
    X = dataframe_to_array(legit)
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
def client(store: InMemoryStore, clock: FrozenClock, scorer: BundleScorer) -> TestClient:
    return TestClient(create_app(store=store, clock=clock, scorer=scorer))
