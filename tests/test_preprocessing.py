import copy

import numpy as np
import pytest
import torch

from app.config import load_config
from app.preprocessing import FacePreprocessor


@pytest.fixture
def input_config():
    return copy.deepcopy(load_config()["input"])


@pytest.mark.parametrize("mode,expected", [
    ("current", [-1.0, 2 * 127 / 255 - 1, 2 * 128 / 255 - 1, 1.0]),
    ("imagenet", [(p / 255 - 0.485) / 0.229 for p in (0, 127, 128, 255)]),
    ("arcface128", [(p - 127.5) / 128 for p in (0, 127, 128, 255)]),
])
def test_normalization_modes_pixel_boundaries(input_config, mode, expected):
    image = np.zeros((112, 112, 3), dtype=np.uint8)
    image[0, :4, :] = np.array([0, 127, 128, 255], dtype=np.uint8)[:, None]
    output = FacePreprocessor(input_config, mode)(image)
    assert output.shape == (1, 3, 112, 112)
    assert output.dtype == torch.float32
    assert output[0, 0, 0, :4].numpy() == pytest.approx(expected, abs=1e-6)


def test_imagenet_preserves_rgb_channel_order(input_config):
    image = np.zeros((112, 112, 3), dtype=np.uint8)
    image[0, 0] = [255, 0, 0]
    output = FacePreprocessor(input_config, "imagenet")(image)[0, :, 0, 0].numpy()
    expected = [(1 - 0.485) / 0.229, -0.456 / 0.224, -0.406 / 0.225]
    assert output == pytest.approx(expected, abs=1e-6)


def test_default_is_backward_compatible_current_mode(input_config):
    image = np.full((112, 112, 3), 64, dtype=np.uint8)
    default = FacePreprocessor(input_config)
    assert default.mode == "current"
    assert default.version == "preprocess-rgb-mean05-v1"
    assert torch.equal(default(image), FacePreprocessor(input_config, "current")(image))


def test_rejects_preprocessed_float_input_to_prevent_double_normalization(input_config):
    with pytest.raises(ValueError, match="uint8"):
        FacePreprocessor(input_config)(np.zeros((112, 112, 3), dtype=np.float32))


def test_unknown_mode_rejected(input_config):
    with pytest.raises(ValueError, match="Unsupported"):
        FacePreprocessor(input_config, "unknown")
