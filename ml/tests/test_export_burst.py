import pandas as pd

from ml.export_burst import select_burst_rows
from ml.features import FEATURE_COLUMNS


def _df(n_fraud: int) -> pd.DataFrame:
    rows = []
    for i in range(20):
        row = {name: 0.0 for name in FEATURE_COLUMNS}
        row["Time"] = float(i)
        row["Class"] = 1 if i < n_fraud else 0
        row["Amount"] = 10.0 + i
        rows.append(row)
    return pd.DataFrame(rows)


def test_select_burst_rows_only_class_one_without_replacement() -> None:
    df = _df(n_fraud=8)
    selected = select_burst_rows(df, size=5, random_state=42)
    assert len(selected) == 5
    assert set(selected["Class"].tolist()) == {1}
    assert selected.duplicated(subset=list(FEATURE_COLUMNS) + ["Amount"]).sum() == 0


def test_select_burst_rows_with_replacement_when_fewer_than_size() -> None:
    df = _df(n_fraud=3)
    selected = select_burst_rows(df, size=5, random_state=42)
    assert len(selected) == 5
    assert set(selected["Class"].tolist()) == {1}
