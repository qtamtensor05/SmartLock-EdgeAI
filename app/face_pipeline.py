from __future__ import annotations

import time
from dataclasses import dataclass

import cv2
import numpy as np

from app.face_alignment import align_face
from app.face_database import FaceDatabase
from app.face_matcher import FaceMatcher
from app.jpeg_decoder import InvalidJPEGError, JPEGDecoder
from app.mobilefacenet import MobileFaceNet
from app.preprocessing import FacePreprocessor
from app.schemas import PipelineStatus


@dataclass(frozen=True)
class PipelineResult:
    status: PipelineStatus
    processing_ms: float
    person_id: str | None = None
    similarity: float | None = None
    embedding: np.ndarray | None = None


class FacePipeline:
    """Priority: readiness -> valid JPEG -> light -> face count -> inference/match."""

    def __init__(self, decoder: JPEGDecoder, detector, preprocessor: FacePreprocessor,
                 embedder: MobileFaceNet, matcher: FaceMatcher, database: FaceDatabase,
                 low_light_mean_luma: float = 35.0):
        self.decoder, self.detector, self.preprocessor = decoder, detector, preprocessor
        self.embedder, self.matcher, self.database = embedder, matcher, database
        self.low_light_mean_luma = low_light_mean_luma

    def process(self, payload: bytes, include_embedding: bool = False) -> PipelineResult:
        started = time.perf_counter()
        try:
            frame = self.decoder.decode(payload)
        except InvalidJPEGError:
            return self._result(PipelineStatus.INVALID_FRAME, started)
        luma = cv2.cvtColor(frame.rgb, cv2.COLOR_RGB2GRAY).mean()
        if luma < self.low_light_mean_luma:
            return self._result(PipelineStatus.LOW_LIGHT, started)
        try:
            detections = self.detector.detect(frame.rgb)
            if not detections:
                return self._result(PipelineStatus.NO_FACE, started)
            if len(detections) > 1:
                return self._result(PipelineStatus.MULTIPLE_FACES, started)
            aligned = align_face(frame.rgb, detections[0].landmarks)
            embedded = self.embedder.embed(self.preprocessor(aligned))
            match = self.matcher.match(embedded.normalized, self.database.candidates())
            return self._result(PipelineStatus.MATCHED if match.matched else PipelineStatus.UNKNOWN,
                                started, match.person_id, match.similarity,
                                embedded.normalized if include_embedding else None)
        except Exception:
            return self._result(PipelineStatus.NOT_READY, started)

    @staticmethod
    def _result(status, started, person_id=None, similarity=None, embedding=None):
        return PipelineResult(status, (time.perf_counter() - started) * 1000,
                              person_id, similarity, embedding)
