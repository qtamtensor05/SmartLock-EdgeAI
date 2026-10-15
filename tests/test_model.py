import numpy as np
import torch

from app.mobilefacenet import MobileFaceNet


def test_real_model_load_and_output():
    model = MobileFaceNet("models/mobilefacenet_scripted.pt")
    result = model.embed(torch.zeros((1, 3, 112, 112), dtype=torch.float32))
    assert result.raw.shape == (128,)
    assert np.isfinite(result.raw).all()
    assert np.isclose(np.linalg.norm(result.normalized), 1.0)
