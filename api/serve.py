from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import QuantileTransformer, StandardScaler

from api.schemas import ScoreRequest
from ml.features import features_to_array

ARTIFACTS_DIR = Path("ml/artifacts")


@dataclass
class ModelBundle:
    scaler: StandardScaler
    isolation_forest: IsolationForest
    if_cdf: QuantileTransformer
    autoencoder: Any | None = None
    ae_cdf: QuantileTransformer | None = None


class Scorer(Protocol):
    def score(self, transaction: ScoreRequest, model: str = "isolation_forest") -> float: ...


def _clip_unit(value: float) -> float:
    return float(min(1.0, max(0.0, value)))


def score_with_bundle(
    bundle: ModelBundle, transaction: ScoreRequest, model: str = "isolation_forest"
) -> float:
    # Features is Time+V1..V28; Amount is a sibling field on ScoreRequest.
    feats = transaction.features.model_dump()
    feats["Amount"] = transaction.amount
    X = bundle.scaler.transform(features_to_array(feats).reshape(1, -1))
    if model == "isolation_forest":
        raw = -bundle.isolation_forest.score_samples(X)
        percentile = bundle.if_cdf.transform(raw.reshape(-1, 1)).ravel()[0]
        return _clip_unit(float(percentile))
    if model == "autoencoder":
        if bundle.autoencoder is None or bundle.ae_cdf is None:
            raise LookupError("autoencoder weights not loaded")
        recon = bundle.autoencoder.reconstruct(X)
        raw = np.mean((X - recon) ** 2, axis=1, keepdims=True)
        percentile = bundle.ae_cdf.transform(raw).ravel()[0]
        return _clip_unit(float(percentile))
    raise ValueError("unknown model")


class BundleScorer:
    def __init__(self, bundle: ModelBundle) -> None:
        self._bundle = bundle

    def score(self, transaction: ScoreRequest, model: str = "isolation_forest") -> float:
        return score_with_bundle(self._bundle, transaction, model=model)


class ConstScorer:
    def __init__(self, value: float, model_name: str = "isolation_forest") -> None:
        self._value = value
        self.model_name = model_name

    def score(self, transaction: ScoreRequest, model: str = "isolation_forest") -> float:
        if model not in {"isolation_forest", "autoencoder"}:
            raise ValueError("unknown model")
        if model == "autoencoder":
            raise LookupError("autoencoder weights not loaded")
        return self._value


def load_bundle(dest_dir: Path = ARTIFACTS_DIR) -> ModelBundle:
    return ModelBundle(
        scaler=joblib.load(dest_dir / "scaler.joblib"),
        isolation_forest=joblib.load(dest_dir / "isolation_forest.joblib"),
        if_cdf=joblib.load(dest_dir / "if_cdf.joblib"),
    )
