import numpy as np
import pytest

from app.face_alignment import align_face


def test_alignment_returns_112_rgb(landmarks):
    image = np.full((120, 160, 3), 127, dtype=np.uint8)
    result = align_face(image, landmarks)
    assert result.shape == (112, 112, 3)
    assert result.dtype == np.uint8


@pytest.mark.parametrize("bad", [np.zeros((4, 2)), np.full((5, 2), np.nan)])
def test_invalid_landmarks_rejected(bad):
    with pytest.raises(ValueError):
        align_face(np.zeros((120, 160, 3), dtype=np.uint8), bad)
