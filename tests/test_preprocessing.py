import numpy as np
import torch

from app.preprocessing import FacePreprocessor


def test_preprocessing_shape_and_values():
    config = {"color_space": "RGB", "tensor_layout": "NCHW", "height": 112, "width": 112,
              "normalization": {"scale": 1 / 255, "mean": [0.5] * 3, "std": [0.5] * 3}}
    output = FacePreprocessor(config)(np.zeros((112, 112, 3), dtype=np.uint8))
    assert output.shape == (1, 3, 112, 112)
    assert output.dtype == torch.float32
    assert torch.allclose(output, torch.full_like(output, -1.0))
