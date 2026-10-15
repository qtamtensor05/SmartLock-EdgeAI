from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path

import numpy as np
import torch


@dataclass(frozen=True)
class EmbeddingResult:
    raw: np.ndarray
    normalized: np.ndarray


class MobileFaceNet:
    def __init__(self, path: str | Path, embedding_dim: int = 128, device: str = "cpu",
                 expected_sha256: str | None = None):
        self.path = Path(path)
        self.embedding_dim = embedding_dim
        self.device = torch.device(device)
        if not self.path.is_file():
            raise FileNotFoundError(f"TorchScript model not found: {self.path}")
        self.checkpoint_sha256 = hashlib.sha256(self.path.read_bytes()).hexdigest()
        if expected_sha256 and self.checkpoint_sha256 != expected_sha256.lower():
            raise ValueError("TorchScript checkpoint SHA-256 mismatch")
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
