from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from sklearn.metrics import (
    average_precision_score,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
)


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
