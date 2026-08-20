from __future__ import annotations

import numpy as np
import torch
from torch import nn


class Autoencoder(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(30, 14),
            nn.ReLU(),
            nn.Linear(14, 7),
            nn.ReLU(),
            nn.Linear(7, 14),
            nn.ReLU(),
            nn.Linear(14, 30),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)

    def reconstruct(self, X: np.ndarray) -> np.ndarray:
        self.eval()
        with torch.no_grad():
            tensor = torch.from_numpy(np.asarray(X, dtype=np.float32))
            return self.forward(tensor).cpu().numpy()
