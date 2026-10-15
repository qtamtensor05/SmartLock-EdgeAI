from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch


@dataclass(frozen=True)
class EmbeddingResult:
    raw: np.ndarray
    normalized: np.ndarray


class MobileFaceNet:
    def __init__(self, path: str | Path, embedding_dim: int = 128, device: str = "cpu"):
        self.path = Path(path)
        self.embedding_dim = embedding_dim
        self.device = torch.device(device)
        if not self.path.is_file():
            raise FileNotFoundError(f"TorchScript model not found: {self.path}")
        self.model = torch.jit.load(str(self.path), map_location=self.device)
        self.model.eval()

    def embed(self, tensor: torch.Tensor) -> EmbeddingResult:
        if tensor.shape != (1, 3, 112, 112) or tensor.dtype != torch.float32:
            raise ValueError("Model input must be float32 [1, 3, 112, 112]")
        with torch.inference_mode():
            output = self.model(tensor.to(self.device))
        if not isinstance(output, torch.Tensor) or output.shape != (1, self.embedding_dim):
            raise RuntimeError(f"Expected model output [1, {self.embedding_dim}]")
        if not torch.isfinite(output).all():
            raise RuntimeError("Model output contains NaN or Inf")
        raw = output[0].detach().cpu().numpy().astype(np.float32, copy=True)
        norm = float(np.linalg.norm(raw))
        if not np.isfinite(norm) or norm <= 1e-12:
            raise RuntimeError("Model produced a zero or invalid embedding")
        return EmbeddingResult(raw=raw, normalized=raw / norm)
