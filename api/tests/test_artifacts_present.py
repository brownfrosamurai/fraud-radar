from pathlib import Path

from api.burst import BURST_PAYLOAD_PATH, load_burst_rows
from api.serve import BundleScorer, load_bundle


def test_artifacts_present() -> None:
    for name in ("scaler.joblib", "isolation_forest.joblib", "if_cdf.joblib", "burst_payload.json"):
        assert (Path("ml/artifacts") / name).is_file(), name
    rows = load_burst_rows(BURST_PAYLOAD_PATH)
    score = BundleScorer(load_bundle()).score(rows[0], model="isolation_forest")
    assert 0.0 <= score <= 1.0
