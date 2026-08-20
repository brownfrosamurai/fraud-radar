from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    import pandas as pd

FEATURE_COLUMNS: tuple[str, ...] = ("Time",) + tuple(f"V{i}" for i in range(1, 29)) + ("Amount",)


def features_to_array(features: Any) -> np.ndarray:
    if hasattr(features, "model_dump"):
        data = features.model_dump()
    else:
        data = dict(features)
    return np.asarray([float(data[name]) for name in FEATURE_COLUMNS], dtype=np.float64)


def dataframe_to_array(df: pd.DataFrame) -> np.ndarray:
    return df.loc[:, list(FEATURE_COLUMNS)].to_numpy(dtype=np.float64)
