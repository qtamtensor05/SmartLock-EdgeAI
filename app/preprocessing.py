from __future__ import annotations

import numpy as np
import torch

NORMALIZATION_MODES = {"current", "imagenet", "arcface128"}


class FacePreprocessor:
    def __init__(self, config: dict, mode: str | None = None):
        self.config = config
        if config.get("color_space") != "RGB" or config.get("tensor_layout") != "NCHW":
            raise ValueError("Only the documented RGB/NCHW contract is supported")
        normalization = config["normalization"]
        # Backward-compatible flat normalization remains supported for old callers.
        if "modes" not in normalization:
            self.mode = mode or normalization.get("mode", "current")
            self.normalization = normalization
            self.version = normalization.get("version", "preprocess-rgb-mean05-v1")
        else:
            self.mode = mode or normalization["mode"]
            if self.mode not in NORMALIZATION_MODES or self.mode not in normalization["modes"]:
                raise ValueError(f"Unsupported normalization mode: {self.mode}")
            self.normalization = normalization["modes"][self.mode]
            self.version = self.normalization["version"]

    @property
    def metadata(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "version": self.version,
            "colorSpace": "RGB",
            "inputSize": [int(self.config["width"]), int(self.config["height"])],
            "tensorLayout": "NCHW",
            "dtype": "float32",
            "formula": self.normalization["formula"],
        }

    def __call__(self, rgb: np.ndarray) -> torch.Tensor:
        expected = (int(self.config["height"]), int(self.config["width"]), 3)
        if rgb.shape != expected or rgb.dtype != np.uint8:
            raise ValueError(f"Preprocessing expects RGB uint8 shape {expected}")
        norm = self.normalization
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
