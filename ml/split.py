from __future__ import annotations

import pandas as pd


def time_ordered_split(
    df: pd.DataFrame, train_frac: float = 0.8
) -> tuple[pd.DataFrame, pd.DataFrame]:
    ordered = df.sort_values("Time", kind="mergesort").reset_index(drop=True)
    cut = int(len(ordered) * train_frac)
    return ordered.iloc[:cut].copy(), ordered.iloc[cut:].copy()
