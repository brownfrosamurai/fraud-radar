from datetime import datetime, timezone
from uuid import uuid4

import numpy as np

from api.explain import explain, permutation_top5, reconstruction_top5, row_vector
from api.schemas import Features, FeatureContribution, ScoredTransaction
from api.tests.conftest import tiny_if_bundle
from ml.features import FEATURE_COLUMNS


def _row(*, amount: float, v14: float = 0.0, model_name: str = "isolation_forest") -> ScoredTransaction:
    feats = {name: 0.0 for name in FEATURE_COLUMNS if name != "Amount"}
    feats["V14"] = v14
    return ScoredTransaction(
        id=uuid4(),
        occurred_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        amount=amount,
        model_score=0.5,
        decision="ALLOW",
        model_name=model_name,  # type: ignore[arg-type]
        features=Features.model_validate(feats),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def test_row_vector_puts_amount_last() -> None:
    vec = row_vector(_row(amount=600.0, v14=1.5))
    assert vec.shape == (30,)
    assert vec[-1] == 600.0
    assert vec[list(FEATURE_COLUMNS).index("V14")] == 1.5


def test_permutation_top5_shape_and_order() -> None:
    bundle = tiny_if_bundle()
    background = np.zeros((8, 30))
    items = permutation_top5(bundle, _row(amount=600.0, v14=4.0), background)
    assert len(items) == 5
    names = {item.feature for item in items}
    assert names <= set(FEATURE_COLUMNS)
    contribs = [item.contribution for item in items]
    assert contribs == sorted(contribs, reverse=True)
    assert all(c >= 0 for c in contribs)


def test_permutation_differs_for_different_rows() -> None:
    bundle = tiny_if_bundle()
    background = np.random.default_rng(0).normal(size=(8, 30))
    a = permutation_top5(bundle, _row(amount=20.0, v14=0.0), background)
    b = permutation_top5(bundle, _row(amount=900.0, v14=8.0), background)
    assert [x.model_dump() for x in a] != [x.model_dump() for x in b]


def test_permutation_is_stable_with_seed() -> None:
    bundle = tiny_if_bundle()
    background = np.random.default_rng(1).normal(size=(8, 30))
    row = _row(amount=400.0, v14=2.0)
    first = permutation_top5(bundle, row, background, seed=42)
    second = permutation_top5(bundle, row, background, seed=42)
    assert [x.model_dump() for x in first] == [x.model_dump() for x in second]


def test_explain_ae_without_weights_raises() -> None:
    bundle = tiny_if_bundle()
    try:
        explain(_row(amount=20.0, model_name="autoencoder"), bundle, background=np.zeros((8, 30)))
    except LookupError as exc:
        assert "autoencoder" in str(exc).lower()
    else:
        raise AssertionError("expected LookupError")


class _FakeAE:
    def reconstruct(self, X: np.ndarray) -> np.ndarray:
        out = np.zeros_like(X)
        out[..., 0] = 0.0
        return out


def test_reconstruction_top5_from_fake_ae() -> None:
    bundle = tiny_if_bundle()
    bundle.autoencoder = _FakeAE()
    bundle.ae_cdf = bundle.if_cdf
    items = reconstruction_top5(bundle, _row(amount=50.0, v14=3.0))
    assert len(items) == 5
    assert all(item.contribution >= 0 for item in items)
