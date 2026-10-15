import numpy as np
import pytest

from app.face_alignment import ARCFACE_TEMPLATE_112, align_face


def test_alignment_returns_112_rgb(landmarks):
    image = np.full((120, 160, 3), 127, dtype=np.uint8)
    result = align_face(image, landmarks)
    assert result.shape == (112, 112, 3)
    assert result.dtype == np.uint8


@pytest.mark.parametrize("bad", [np.zeros((4, 2)), np.full((5, 2), np.nan)])
def test_invalid_landmarks_rejected(bad):
    with pytest.raises(ValueError):
        align_face(np.zeros((120, 160, 3), dtype=np.uint8), bad)


def test_alignment_template_is_versioned_square_112_contract():
    expected = np.array([[38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366],
                         [41.5493, 92.3655], [70.7299, 92.2041]], dtype=np.float32)
    assert ARCFACE_TEMPLATE_112.shape == (5, 2)
    assert np.array_equal(ARCFACE_TEMPLATE_112, expected)
