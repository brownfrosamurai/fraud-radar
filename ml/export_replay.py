from pathlib import Path

import pandas as pd

from ml.export_burst import rows_to_payload
from ml.features import FEATURE_COLUMNS  # noqa: F401  # used by callers

REPLAY_PAYLOAD_PATH = Path("ml/artifacts/replay_payload.json")
REPLAY_SIZE = 200
REPLAY_FRAUD = 20
REPLAY_RANDOM_STATE = 42


def select_replay_rows(
    test_df: pd.DataFrame,
    size: int = REPLAY_SIZE,
    n_fraud: int = REPLAY_FRAUD,
    random_state: int = REPLAY_RANDOM_STATE,
) -> pd.DataFrame:
    fraud = test_df[test_df["Class"] == 1]
    legit = test_df[test_df["Class"] == 0]
    nf = min(n_fraud, len(fraud), size)
    nl = size - nf
    f = fraud.sample(n=nf, random_state=random_state)
    l = legit.sample(n=nl, random_state=random_state)
    return pd.concat([f, l]).sample(frac=1, random_state=random_state).reset_index(drop=True)


def write_replay_payload(df: pd.DataFrame, path: Path = REPLAY_PAYLOAD_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(__import__("json").dumps(rows_to_payload(df)))
    return path
