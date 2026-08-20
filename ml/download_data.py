from __future__ import annotations

from pathlib import Path


def download_creditcard(dest: Path) -> Path:
    import kagglehub

    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    cached = Path(kagglehub.dataset_download("mlg-ulb/creditcardfraud"))
    matches = list(cached.rglob("creditcard.csv"))
    if not matches:
        raise FileNotFoundError("creditcard.csv not in kagglehub cache")
    dest.write_bytes(matches[0].read_bytes())
    return dest
