import numpy as np
import torch

from ml.autoencoder import Autoencoder
from ml import evaluate
from ml.evaluate import binary_at_threshold, evaluate_model
from ml.train_autoencoder import fit_autoencoder, raw_ae_score


def test_evaluate_does_not_retrain_or_overwrite_metrics() -> None:
    assert not hasattr(evaluate, "compare_models")
    assert not hasattr(evaluate, "main")



def test_evaluate_model_keys_exclude_accuracy() -> None:
    y = np.array([0, 0, 1, 1])
    scores = np.array([0.1, 0.2, 0.95, 0.99])
    metrics = evaluate_model(y, scores, block_threshold=0.9)
    assert set(metrics) == {"pr_auc", "precision", "recall", "f1"}
    assert "accuracy" not in metrics
    assert metrics["precision"] == 1.0
    assert metrics["recall"] == 1.0


def test_binary_at_block_line() -> None:
    scores = np.array([0.899, 0.9, 0.91])
    np.testing.assert_array_equal(binary_at_threshold(scores, 0.9), np.array([0, 1, 1]))


def test_autoencoder_architecture_and_recon_shape() -> None:
    model = Autoencoder()
    linear_out = [m.out_features for m in model.modules() if isinstance(m, torch.nn.Linear)]
    assert linear_out == [14, 7, 14, 30]
    x = torch.zeros(2, 30)
    assert model(x).shape == (2, 30)


def test_fit_autoencoder_raw_scores_non_negative() -> None:
    rng = np.random.default_rng(0)
    X = rng.normal(size=(40, 30)).astype(np.float32)
    model = fit_autoencoder(X, epochs=1, batch_size=16, seed=42)
    raw = raw_ae_score(model, X)
    assert raw.shape == (40,)
    assert np.all(raw >= 0.0)


def test_save_pr_curve_writes_nonempty_png(tmp_path) -> None:
    from ml.evaluate import save_pr_curve

    y = np.array([0, 0, 1, 1])
    dest = tmp_path / "pr.png"
    save_pr_curve(y, {"model": np.array([0.1, 0.2, 0.95, 0.99])}, dest)
    assert dest.is_file()
    assert dest.stat().st_size > 0
