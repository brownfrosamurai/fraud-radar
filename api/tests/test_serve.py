from api.schemas import ScoreRequest
from api.serve import BundleScorer, score_with_bundle
from api.tests.conftest import sample_request, tiny_if_bundle


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
