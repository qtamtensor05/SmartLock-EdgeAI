import json

import numpy as np
import pytest

from app.face_database import FaceDatabase


def test_enroll_list_delete(tmp_path):
    path = tmp_path / "faces.json"
    database = FaceDatabase(path, "v1", embedding_dim=3)
    assert database.enroll("user-1", np.array([1, 0, 0])) == 1
    assert database.list_persons() == [{"personId": "user-1", "sampleCount": 1}]
    assert database.delete("user-1") is True
    assert database.delete("user-1") is False


def test_model_version_mismatch(tmp_path):
    path = tmp_path / "faces.json"
    path.write_text(json.dumps({"schemaVersion": "1.0", "modelVersion": "old",
                                "embeddingDim": 3, "persons": {}}), encoding="utf-8")
    with pytest.raises(ValueError, match="mismatch"):
        FaceDatabase(path, "new", embedding_dim=3)


def test_preprocessing_pipeline_version_mismatch(tmp_path):
    path = tmp_path / "faces.json"
    first = FaceDatabase(path, "v1", embedding_dim=3, pipeline_version="pipeline-current")
    first.enroll("user-1", np.array([1, 0, 0]))
    with pytest.raises(ValueError, match="pipeline version mismatch"):
        FaceDatabase(path, "v1", embedding_dim=3, pipeline_version="pipeline-imagenet")


def test_legacy_database_is_only_accepted_explicitly(tmp_path):
    path = tmp_path / "faces.json"
    path.write_text(json.dumps({"schemaVersion": "1.0", "modelVersion": "v1",
                                "embeddingDim": 3, "persons": {}}), encoding="utf-8")
    compatible = FaceDatabase(path, "v1", embedding_dim=3,
                              pipeline_version="pipeline-current", allow_legacy_pipeline=True)
    assert compatible.list_persons() == []
    with pytest.raises(ValueError, match="no preprocessing pipeline version"):
        FaceDatabase(path, "v1", embedding_dim=3,
                     pipeline_version="pipeline-other", allow_legacy_pipeline=False)
