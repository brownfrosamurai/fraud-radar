from pathlib import Path


def test_if_artifacts_exist() -> None:
    root = Path("ml/artifacts")
    for name in ("scaler.joblib", "isolation_forest.joblib", "if_cdf.joblib", "burst_payload.json"):
        assert (root / name).is_file(), name
