import numpy as np
import pandas as pd

from ml.features import FEATURE_COLUMNS
from ml.train_isolation_forest import fit_isolation_forest, raw_if_score


def _synth(n_legit: int = 80, n_fraud: int = 8) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    rows = []
    for _ in range(n_legit):
        row = {name: float(rng.normal()) for name in FEATURE_COLUMNS}
        row["Class"] = 0
        rows.append(row)
    for _ in range(n_fraud):
        row = {name: float(rng.normal() + 8.0) for name in FEATURE_COLUMNS}
        row["Class"] = 1
        rows.append(row)
    return pd.DataFrame(rows)


def test_if_cdf_ranks_outliers_higher_than_inliers() -> None:
    df = _synth()
    legit = df[df["Class"] == 0]
    scaler, model, cdf = fit_isolation_forest(legit)
    from ml.features import dataframe_to_array

    X = scaler.transform(dataframe_to_array(df))
    raw = raw_if_score(model, X)
    scores = np.clip(cdf.transform(raw.reshape(-1, 1)).ravel(), 0.0, 1.0)
    mean_legit = float(scores[df["Class"] == 0].mean())
    mean_fraud = float(scores[df["Class"] == 1].mean())
    assert mean_fraud > mean_legit
    assert scores.min() >= 0.0
    assert scores.max() <= 1.0


def test_raw_if_score_is_negated_score_samples() -> None:
    df = _synth()
    scaler, model, _cdf = fit_isolation_forest(df[df["Class"] == 0])
    from ml.features import dataframe_to_array

    X = scaler.transform(dataframe_to_array(df.iloc[:5]))
    np.testing.assert_allclose(raw_if_score(model, X), -model.score_samples(X))
