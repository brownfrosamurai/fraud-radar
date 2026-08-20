from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
)

CSV_PATH = Path("data/raw/creditcard.csv")
METRICS_PATH = Path("ml/artifacts/metrics.json")
PR_CURVE_PATH = Path("ml/artifacts/pr_curve.png")


def binary_at_threshold(scores: np.ndarray, threshold: float = 0.9) -> np.ndarray:
    return (np.asarray(scores) >= threshold).astype(int)


def evaluate_model(
    y_true: np.ndarray, scores: np.ndarray, block_threshold: float = 0.9
) -> dict[str, float]:
    y_pred = binary_at_threshold(scores, block_threshold)
    return {
        "pr_auc": float(average_precision_score(y_true, scores)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
    }


def save_pr_curve(
    y_true: np.ndarray, score_series: dict[str, np.ndarray], dest: Path
) -> None:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots()
    for name, scores in score_series.items():
        precision, recall, _thresholds = precision_recall_curve(y_true, scores)
        ax.plot(recall, precision, label=name)
    ax.set_xlabel("Recall")
    ax.set_ylabel("Precision")
    ax.legend()
    fig.savefig(dest)
    plt.close(fig)


def compare_models(
    train_df: pd.DataFrame, test_df: pd.DataFrame
) -> tuple[dict[str, dict[str, float]], dict[str, np.ndarray], np.ndarray]:
    from sklearn.preprocessing import QuantileTransformer

    from ml.features import dataframe_to_array
    from ml.train_autoencoder import fit_autoencoder, raw_ae_score
    from ml.train_isolation_forest import fit_isolation_forest, raw_if_score

    train_legit = train_df[train_df["Class"] == 0]
    scaler, if_model, if_cdf = fit_isolation_forest(train_legit)
    X_train = scaler.transform(dataframe_to_array(train_legit))
    ae = fit_autoencoder(X_train, epochs=10, batch_size=256, seed=42)

    X_test = scaler.transform(dataframe_to_array(test_df))
    y_true = test_df["Class"].to_numpy()

    if_raw = raw_if_score(if_model, X_test)
    if_scores = np.clip(if_cdf.transform(if_raw.reshape(-1, 1)).ravel(), 0.0, 1.0)

    ae_train_raw = raw_ae_score(ae, X_train)
    n_quantiles = min(1000, max(2, len(ae_train_raw)))
    ae_cdf = QuantileTransformer(
        output_distribution="uniform", n_quantiles=n_quantiles, random_state=42
    )
    ae_cdf.fit(ae_train_raw.reshape(-1, 1))
    ae_raw = raw_ae_score(ae, X_test)
    ae_scores = np.clip(ae_cdf.transform(ae_raw.reshape(-1, 1)).ravel(), 0.0, 1.0)

    metrics = {
        "isolation_forest": evaluate_model(y_true, if_scores),
        "autoencoder": evaluate_model(y_true, ae_scores),
    }
    return metrics, {"isolation_forest": if_scores, "autoencoder": ae_scores}, y_true


def main() -> None:
    if not CSV_PATH.exists():
        print("data/raw/creditcard.csv not found; skip training (no Kaggle download)")
        if METRICS_PATH.exists():
            print(json.loads(METRICS_PATH.read_text()))
        else:
            print("run ml/evaluate.py after training")
        return

    from ml.split import time_ordered_split

    df = pd.read_csv(CSV_PATH)
    train_df, test_df = time_ordered_split(df)
    metrics, series, y_true = compare_models(train_df, test_df)
    METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    METRICS_PATH.write_text(json.dumps(metrics, indent=2) + "\n")
    save_pr_curve(y_true, series, PR_CURVE_PATH)
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
