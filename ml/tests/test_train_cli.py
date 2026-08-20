from pathlib import Path

from ml.train import main


def test_train_exits_when_csv_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(csv_path=tmp_path / "missing.csv") == 1
