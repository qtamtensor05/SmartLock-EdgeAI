from types import SimpleNamespace

import numpy as np

from app.face_database import FaceDatabase
from app.face_detector import FaceDetection
from app.face_matcher import FaceMatcher
from app.face_pipeline import FacePipeline
from app.jpeg_decoder import JPEGDecoder
from app.mobilefacenet import EmbeddingResult
from app.schemas import PipelineStatus


class Detector:
    def __init__(self, count, landmarks): self.count, self.landmarks = count, landmarks
    def detect(self, _): return [FaceDetection((0, 0, 10, 10), .9, self.landmarks) for _ in range(self.count)]


class Preprocessor:
    def __call__(self, _): return object()


class Embedder:
    def __init__(self, fail=False): self.fail = fail
    def embed(self, _):
        if self.fail: raise RuntimeError("model unavailable")
        vector = np.ones(128, dtype=np.float32) / np.sqrt(128)
        return EmbeddingResult(vector, vector)


def pipeline(tmp_path, landmarks, count=1, fail=False, low_light=0):
    return FacePipeline(JPEGDecoder(), Detector(count, landmarks), Preprocessor(), Embedder(fail),
                        FaceMatcher(.65), FaceDatabase(tmp_path / "db.json", "v1"), low_light)


def test_pipeline_face_states(tmp_path, landmarks, jpeg_factory):
    assert pipeline(tmp_path, landmarks, 0).process(jpeg_factory()).status == PipelineStatus.NO_FACE
    assert pipeline(tmp_path, landmarks, 2).process(jpeg_factory()).status == PipelineStatus.MULTIPLE_FACES
    assert pipeline(tmp_path, landmarks, 1).process(jpeg_factory()).status == PipelineStatus.UNKNOWN


def test_pipeline_invalid_low_light_and_fail_closed(tmp_path, landmarks, jpeg_factory):
    assert pipeline(tmp_path, landmarks).process(b"bad").status == PipelineStatus.INVALID_FRAME
    assert pipeline(tmp_path, landmarks, low_light=250).process(jpeg_factory()).status == PipelineStatus.LOW_LIGHT
    assert pipeline(tmp_path, landmarks, fail=True).process(jpeg_factory()).status == PipelineStatus.NOT_READY
