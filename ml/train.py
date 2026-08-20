from __future__ import annotations

from pathlib import Path
import json
import sys

DEFAULT_CSV = Path("data/raw/creditcard.csv")
ARTIFACTS_DIR = Path("ml/artifacts")


def main(csv_path: Path = DEFAULT_CSV) -> int:
    if not csv_path.exists():
        print("missing dataset; run: python -m ml.download_data", file=sys.stderr)
        return 1

    import joblib
    import numpy as np
    import pandas as pd
    import torch
    from sklearn.preprocessing import QuantileTransformer

    from ml.evaluate import evaluate_model, save_pr_curve
    from ml.export_burst import select_burst_rows, write_burst_payload
    from ml.export_replay import select_replay_rows, write_replay_payload
    from ml.features import dataframe_to_array
    from ml.split import time_ordered_split
    from ml.train_autoencoder import fit_autoencoder, raw_ae_score
    from ml.train_isolation_forest import (
        fit_isolation_forest,
        raw_if_score,
        save_if_artifacts,
    )

    df = pd.read_csv(csv_path)
    train_df, test_df = time_ordered_split(df)
    train_legit = train_df[train_df["Class"] == 0]
    scaler, if_model, if_cdf = fit_isolation_forest(train_legit)
    save_if_artifacts(scaler, if_model, if_cdf, ARTIFACTS_DIR)

    X_train = scaler.transform(dataframe_to_array(train_legit))
    ae = fit_autoencoder(X_train, epochs=10, batch_size=256, seed=42)
    ae_train_raw = raw_ae_score(ae, X_train)
    n_quantiles = min(1000, max(2, len(ae_train_raw)))
    ae_cdf = QuantileTransformer(
        output_distribution="uniform", n_quantiles=n_quantiles, random_state=42
    )
    ae_cdf.fit(ae_train_raw.reshape(-1, 1))
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    torch.save(ae.state_dict(), ARTIFACTS_DIR / "autoencoder.pt")
    joblib.dump(ae_cdf, ARTIFACTS_DIR / "ae_cdf.joblib")

    write_burst_payload(select_burst_rows(test_df), ARTIFACTS_DIR / "burst_payload.json")
    write_replay_payload(
        select_replay_rows(test_df), ARTIFACTS_DIR / "replay_payload.json"
    )

    X_test = scaler.transform(dataframe_to_array(test_df))
    y_true = test_df["Class"].to_numpy()
    if_raw = raw_if_score(if_model, X_test)
    if_scores = np.clip(if_cdf.transform(if_raw.reshape(-1, 1)).ravel(), 0.0, 1.0)
    ae_raw = raw_ae_score(ae, X_test)
    ae_scores = np.clip(ae_cdf.transform(ae_raw.reshape(-1, 1)).ravel(), 0.0, 1.0)

    metrics = {
        "isolation_forest": evaluate_model(y_true, if_scores),
        "autoencoder": evaluate_model(y_true, ae_scores),
    }
    (ARTIFACTS_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    save_pr_curve(
        y_true,
        {"isolation_forest": if_scores, "autoencoder": ae_scores},
        ARTIFACTS_DIR / "pr_curve.png",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
