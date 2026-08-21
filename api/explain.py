from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from sklearn.ensemble import IsolationForest

from api.schemas import FeatureContribution, ScoredTransaction
from api.serve import ModelBundle
from ml.features import FEATURE_COLUMNS, features_to_array

REPLAY_PATH = Path("ml/artifacts/replay_payload.json")
N_REPEATS = 5
SEED = 42
TOP_K = 5


def row_vector(row: ScoredTransaction) -> np.ndarray:
    data = row.features.model_dump()
    data["Amount"] = row.amount
    return features_to_array(data)


def load_explain_background(path: Path | None = None) -> np.ndarray:
    payload = json.loads((path or REPLAY_PATH).read_text())
    rows = [
        features_to_array({**item["features"], "Amount": item["amount"]})
        for item in payload
    ]
    return np.asarray(rows, dtype=np.float64)


def _scaled(bundle: ModelBundle, vec: np.ndarray) -> np.ndarray:
    return bundle.scaler.transform(vec.reshape(1, -1))


def _anomaly(model: IsolationForest, X: np.ndarray) -> np.ndarray:
    return -model.score_samples(X)


# Not sklearn's permutation_importance: that shuffles a column across a whole X and
# measures the drop in a dataset-level metric. This is instance-level — it swaps this one
# transaction's each feature for sampled background rows and measures the drop in *its*
# anomaly score, to answer "why did this transaction score the way it did."
def permutation_top5(
    bundle: ModelBundle,
    row: ScoredTransaction,
    background: np.ndarray,
    n_repeats: int = N_REPEATS,
    seed: int = SEED,
) -> list[FeatureContribution]:
    x = row_vector(row)
    rng = np.random.default_rng(seed)
    n = min(n_repeats, len(background))
    idx = rng.choice(len(background), size=n, replace=False)
    bg = background[idx]
    x_s = _scaled(bundle, x)
    bg_s = bundle.scaler.transform(bg)
    base = float(_anomaly(bundle.isolation_forest, x_s)[0])
    importances: list[float] = []
    for j in range(len(FEATURE_COLUMNS)):
        X = np.repeat(x_s, n, axis=0)
        X[:, j] = bg_s[:, j]
        perm = _anomaly(bundle.isolation_forest, X)
        importances.append(max(0.0, base - float(perm.mean())))
    ranked = sorted(
        zip(FEATURE_COLUMNS, importances, strict=True),
        key=lambda pair: pair[1],
        reverse=True,
    )[:TOP_K]
    return [FeatureContribution(feature=name, contribution=value) for name, value in ranked]


def reconstruction_top5(
    bundle: ModelBundle, row: ScoredTransaction
) -> list[FeatureContribution]:
    if bundle.autoencoder is None:
        raise LookupError("autoencoder weights not loaded")
    x_s = _scaled(bundle, row_vector(row))
    recon = np.asarray(bundle.autoencoder.reconstruct(x_s), dtype=np.float64)
    err = np.square(x_s - recon).ravel()
    ranked = sorted(
        zip(FEATURE_COLUMNS, err.tolist(), strict=True),
        key=lambda pair: pair[1],
        reverse=True,
    )[:TOP_K]
    return [
        FeatureContribution(feature=name, contribution=max(0.0, float(value)))
        for name, value in ranked
    ]


def explain(
    row: ScoredTransaction,
    bundle: ModelBundle,
    background: np.ndarray | None = None,
) -> list[FeatureContribution]:
    if row.model_name == "autoencoder":
        if bundle.autoencoder is None or bundle.ae_cdf is None:
            raise LookupError("autoencoder weights not loaded")
        return reconstruction_top5(bundle, row)
    bg = background if background is not None else load_explain_background()
    return permutation_top5(bundle, row, bg)
