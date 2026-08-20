import numpy as np
import pandas as pd

from ml.features import FEATURE_COLUMNS, dataframe_to_array, features_to_array


def test_feature_columns_order() -> None:
    assert FEATURE_COLUMNS[0] == "Time"
    assert FEATURE_COLUMNS[-1] == "Amount"
    assert FEATURE_COLUMNS[1:29] == tuple(f"V{i}" for i in range(1, 29))
    assert len(FEATURE_COLUMNS) == 30


def test_features_to_array_shape() -> None:
    payload = {"Time": 1.5, **{f"V{i}": float(i) for i in range(1, 29)}, "Amount": 9.0}
    arr = features_to_array(payload)
    assert arr.shape == (30,)
    assert arr[0] == 1.5
    assert arr[-1] == 9.0
    assert arr[1] == 1.0


def test_dataframe_to_array_uses_column_order_not_df_order() -> None:
    df = pd.DataFrame([{"Amount": 3.0, "Time": 1.0, **{f"V{i}": 0.0 for i in range(1, 29)}}])
    arr = dataframe_to_array(df)
    assert arr.shape == (1, 30)
    np.testing.assert_allclose(arr[0, 0], 1.0)
    np.testing.assert_allclose(arr[0, -1], 3.0)
