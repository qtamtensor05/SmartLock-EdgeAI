from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass(frozen=True)
class FaceDetection:
    bbox: tuple[float, float, float, float]
    confidence: float
    landmarks: np.ndarray


class YuNetFaceDetector:
    """YuNet coordinates are pixels in the original RGB image."""

    def __init__(self, model_path: str | Path, confidence_threshold: float = 0.8,
                 nms_threshold: float = 0.3, top_k: int = 5000):
        path = Path(model_path)
        if not path.is_file():
            raise FileNotFoundError(f"YuNet detector model not found: {path}")
        self._detector = cv2.FaceDetectorYN.create(
            str(path), "", (320, 240), confidence_threshold, nms_threshold, top_k
        )

    def detect(self, rgb: np.ndarray) -> list[FaceDetection]:
        if rgb.ndim != 3 or rgb.shape[2] != 3 or rgb.dtype != np.uint8:
            raise ValueError("Detector expects an RGB uint8 HxWx3 image")
        height, width = rgb.shape[:2]
        self._detector.setInputSize((width, height))
        _, rows = self._detector.detect(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
        if rows is None:
            return []
        results = []
        for row in rows:
            results.append(FaceDetection(
                bbox=tuple(float(v) for v in row[:4]),
                landmarks=np.asarray(row[4:14], dtype=np.float32).reshape(5, 2),
                confidence=float(row[14]),
            ))
        return results
