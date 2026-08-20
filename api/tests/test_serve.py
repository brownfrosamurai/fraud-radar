import numpy as np
import pandas as pd
import pytest
from sklearn.preprocessing import QuantileTransformer

from api.schemas import ScoreRequest
from api.serve import BundleScorer, score_with_bundle
from api.tests.conftest import sample_request, tiny_if_bundle
from ml.features import FEATURE_COLUMNS, dataframe_to_array


def test_score_with_bundle_is_unit_interval() -> None:
    bundle = tiny_if_bundle()
    req = ScoreRequest.model_validate(sample_request(amount=20.0))
    value = score_with_bundle(bundle, req, model="isolation_forest")
    assert 0.0 <= value <= 1.0


def test_bundle_scorer_rejects_unknown_model() -> None:
    scorer = BundleScorer(tiny_if_bundle())
    req = ScoreRequest.model_validate(sample_request())
    try:
        scorer.score(req, model="nope")
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "unknown model" in str(exc)


def test_bundle_scorer_autoencoder_without_weights() -> None:
    scorer = BundleScorer(tiny_if_bundle())
    req = ScoreRequest.model_validate(sample_request())
    try:
        scorer.score(req, model="autoencoder")
        raise AssertionError("expected LookupError")
    except LookupError as exc:
        assert "autoencoder weights not loaded" in str(exc)


def test_bundle_scorer_autoencoder_unit_interval() -> None:
    pytest.importorskip("torch")
    from ml.train_autoencoder import fit_autoencoder, raw_ae_score

    bundle = tiny_if_bundle()
    rng = np.random.default_rng(0)
    legit = pd.DataFrame(
        [{name: float(rng.normal()) for name in FEATURE_COLUMNS} for _ in range(60)]
    )
    Xs = bundle.scaler.transform(dataframe_to_array(legit))
    ae = fit_autoencoder(Xs, epochs=1, batch_size=16, seed=42)
    raw = raw_ae_score(ae, Xs)
    bundle.autoencoder = ae
    bundle.ae_cdf = QuantileTransformer(
        output_distribution="uniform", n_quantiles=min(60, 1000), random_state=42
    ).fit(raw.reshape(-1, 1))
    req = ScoreRequest.model_validate(sample_request())
    value = BundleScorer(bundle).score(req, model="autoencoder")
    assert 0.0 <= value <= 1.0
