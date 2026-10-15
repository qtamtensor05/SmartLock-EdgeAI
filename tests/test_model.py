import numpy as np
import pytest
import torch

from app.mobilefacenet import MobileFaceNet


def test_real_model_load_and_output():
    expected_hash = "780e31e7c2639a0d5fdebe843f5df3ff81fda79a090164df0ff40514d172853a"
    model = MobileFaceNet("models/mobilefacenet_scripted.pt", expected_sha256=expected_hash)
    result = model.embed(torch.zeros((1, 3, 112, 112), dtype=torch.float32))
    assert result.raw.shape == (128,)
    assert np.isfinite(result.raw).all()
    assert np.isclose(np.linalg.norm(result.normalized), 1.0)

    model.model = lambda _tensor: torch.full((1, 128), float("nan"))
    with pytest.raises(RuntimeError, match="NaN or Inf"):
        model.embed(torch.zeros((1, 3, 112, 112), dtype=torch.float32))


def test_invalid_checkpoint_hash_is_rejected():
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        MobileFaceNet("models/mobilefacenet_scripted.pt", expected_sha256="0" * 64)
