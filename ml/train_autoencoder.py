from __future__ import annotations

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from ml.autoencoder import Autoencoder


def raw_ae_score(model: Autoencoder, X: np.ndarray) -> np.ndarray:
    recon = model.reconstruct(X)
    return np.mean((np.asarray(X) - recon) ** 2, axis=1)


def fit_autoencoder(
    train_legit_scaled: np.ndarray,
    epochs: int = 10,
    batch_size: int = 256,
    seed: int = 42,
) -> Autoencoder:
    torch.manual_seed(seed)
    model = Autoencoder()
    opt = torch.optim.Adam(model.parameters())
    loss_fn = nn.MSELoss()
    data = torch.from_numpy(np.asarray(train_legit_scaled, dtype=np.float32))
    loader = DataLoader(TensorDataset(data), batch_size=batch_size, shuffle=True)
    model.train()
    for _ in range(epochs):
        for (batch,) in loader:
            opt.zero_grad()
            pred = model(batch)
            loss = loss_fn(pred, batch)
            loss.backward()
            opt.step()
    return model
