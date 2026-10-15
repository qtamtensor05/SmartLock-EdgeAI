import numpy as np
import pytest

from app.face_matcher import FaceMatcher, cosine_similarity, l2_normalize


def test_cosine_and_one_to_many():
    query = np.array([1, 0], dtype=np.float32)
    assert cosine_similarity(query, query) == pytest.approx(1.0)
    result = FaceMatcher(0.8).match(query, [("other", np.array([0, 1])), ("same", query)])
    assert result.matched and result.person_id == "same"


def test_zero_vector_rejected():
    with pytest.raises(ValueError, match="zero"):
        l2_normalize(np.zeros(128))
