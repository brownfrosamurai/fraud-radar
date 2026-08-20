from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import QuantileTransformer, StandardScaler

from ml.features import dataframe_to_array

IF_N_ESTIMATORS = 100
IF_RANDOM_STATE = 42


def raw_if_score(model: IsolationForest, X: np.ndarray) -> np.ndarray:
    return -model.score_samples(X)


def fit_isolation_forest(
    train_legit: pd.DataFrame,
) -> tuple[StandardScaler, IsolationForest, QuantileTransformer]:
    X = dataframe_to_array(train_legit)
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)
    model = IsolationForest(
        n_estimators=IF_N_ESTIMATORS,
        contamination="auto",
        random_state=IF_RANDOM_STATE,
    )
    model.fit(Xs)
    raw = raw_if_score(model, Xs)
    n_quantiles = min(1000, max(2, len(raw)))
    cdf = QuantileTransformer(
        output_distribution="uniform",
        n_quantiles=n_quantiles,
        random_state=IF_RANDOM_STATE,
    )
    cdf.fit(raw.reshape(-1, 1))
    return scaler, model, cdf


def save_if_artifacts(
    scaler: StandardScaler,
    model: IsolationForest,
    cdf: QuantileTransformer,
    dest_dir: Path,
) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(scaler, dest_dir / "scaler.joblib")
    joblib.dump(model, dest_dir / "isolation_forest.joblib")
    joblib.dump(cdf, dest_dir / "if_cdf.joblib")
