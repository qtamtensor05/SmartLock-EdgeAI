from io import BytesIO

import numpy as np
import pytest
from PIL import Image


@pytest.fixture
def jpeg_factory():
    def make(size=(320, 240), color=(180, 160, 140)):
        buffer = BytesIO()
        Image.new("RGB", size, color).save(buffer, format="JPEG")
        return buffer.getvalue()
    return make


@pytest.fixture
def landmarks():
    return np.array([[38, 52], [74, 52], [56, 72], [42, 92], [71, 92]], dtype=np.float32)
