from __future__ import annotations

import cv2
import numpy as np

ARCFACE_TEMPLATE_112 = np.array([
    [38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366],
    [41.5493, 92.3655], [70.7299, 92.2041],
], dtype=np.float32)


def align_face(rgb: np.ndarray, landmarks: np.ndarray,
               template: np.ndarray = ARCFACE_TEMPLATE_112) -> np.ndarray:
    points = np.asarray(landmarks, dtype=np.float32)
    target = np.asarray(template, dtype=np.float32)
    if rgb.ndim != 3 or rgb.shape[2] != 3 or rgb.dtype != np.uint8:
        raise ValueError("Alignment expects an RGB uint8 HxWx3 image")
    if points.shape != (5, 2) or target.shape != (5, 2):
        raise ValueError("Landmarks and template must have shape (5, 2)")
    if not np.isfinite(points).all() or not np.isfinite(target).all():
        raise ValueError("Landmarks must be finite")
    matrix, _ = cv2.estimateAffinePartial2D(points, target, method=cv2.LMEDS)
    if matrix is None or not np.isfinite(matrix).all():
        raise ValueError("Could not estimate a valid face alignment transform")
    return cv2.warpAffine(rgb, matrix, (112, 112), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=0)
