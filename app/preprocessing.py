from __future__ import annotations

import numpy as np
import torch


class FacePreprocessor:
    def __init__(self, config: dict):
        self.config = config
        if config.get("color_space") != "RGB" or config.get("tensor_layout") != "NCHW":
            raise ValueError("Only the documented RGB/NCHW contract is supported")

    def __call__(self, rgb: np.ndarray) -> torch.Tensor:
        expected = (int(self.config["height"]), int(self.config["width"]), 3)
        if rgb.shape != expected or rgb.dtype != np.uint8:
            raise ValueError(f"Preprocessing expects RGB uint8 shape {expected}")
        norm = self.config["normalization"]
        array = rgb.astype(np.float32) * float(norm["scale"])
        mean = np.asarray(norm["mean"], dtype=np.float32)
        std = np.asarray(norm["std"], dtype=np.float32)
        if mean.shape != (3,) or std.shape != (3,) or np.any(std == 0):
            raise ValueError("Normalization mean/std must contain three valid channels")
        array = (array - mean) / std
        tensor = torch.from_numpy(np.ascontiguousarray(array.transpose(2, 0, 1))).unsqueeze(0)
        if tensor.shape != (1, 3, expected[0], expected[1]) or tensor.dtype != torch.float32:
            raise RuntimeError("Preprocessing contract violation")
        return tensor
