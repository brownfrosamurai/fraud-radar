import pandas as pd

from ml.split import time_ordered_split


def test_time_ordered_split_is_80_20_and_sorted() -> None:
    df = pd.DataFrame(
        {
            "Time": [10, 1, 5, 20, 2],
            "Amount": [1, 2, 3, 4, 5],
            "Class": [0, 1, 0, 0, 1],
            **{f"V{i}": 0.0 for i in range(1, 29)},
        }
    )
    train, test = time_ordered_split(df, train_frac=0.8)
    assert list(train["Time"]) == [1, 2, 5, 10]
    assert list(test["Time"]) == [20]
    assert len(train) + len(test) == 5


def test_split_does_not_put_later_times_in_train() -> None:
    df = pd.DataFrame(
        {
            "Time": list(range(10)),
            "Amount": 0.0,
            "Class": 0,
            **{f"V{i}": 0.0 for i in range(1, 29)},
        }
    )
    train, test = time_ordered_split(df, train_frac=0.8)
    assert train["Time"].max() < test["Time"].min()
