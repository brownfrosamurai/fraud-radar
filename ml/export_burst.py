from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from ml.features import FEATURE_COLUMNS

BURST_PAYLOAD_PATH = Path("ml/artifacts/burst_payload.json")
BURST_SIZE = 50
BURST_RANDOM_STATE = 42


def select_burst_rows(
    test_df: pd.DataFrame, size: int = BURST_SIZE, random_state: int = BURST_RANDOM_STATE
) -> pd.DataFrame:
    fraud = test_df[test_df["Class"] == 1]
    if len(fraud) == 0:
        raise ValueError("no Class==1 rows in test split")
    replace = len(fraud) < size
    return fraud.sample(n=size, replace=replace, random_state=random_state).reset_index(drop=True)


def rows_to_payload(df: pd.DataFrame) -> list[dict]:
    out = []
    for _, row in df.iterrows():
        features = {name: float(row[name]) for name in FEATURE_COLUMNS if name != "Amount"}
        out.append({"amount": float(row["Amount"]), "features": features})
    return out


def write_burst_payload(df: pd.DataFrame, path: Path = BURST_PAYLOAD_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows_to_payload(df)))
    return path
