import pandas as pd

from ml.export_replay import select_replay_rows
from ml.features import FEATURE_COLUMNS


def _df() -> pd.DataFrame:
    rows = []
    for i in range(40):
        row = {name: 0.0 for name in FEATURE_COLUMNS}
        row["Time"] = float(i)
        row["Class"] = 1 if i < 8 else 0
        row["Amount"] = 10.0 + i
        rows.append(row)
    return pd.DataFrame(rows)


def test_select_replay_rows_is_mixed_and_shuffled() -> None:
    selected = select_replay_rows(_df(), size=10, n_fraud=3, random_state=42)
    assert len(selected) == 10
    assert int((selected["Class"] == 1).sum()) == 3
    assert int((selected["Class"] == 0).sum()) == 7
