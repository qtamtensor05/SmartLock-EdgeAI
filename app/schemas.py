from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class PipelineStatus(str, Enum):
    MATCHED = "MATCHED"
    UNKNOWN = "UNKNOWN"
    NO_FACE = "NO_FACE"
    MULTIPLE_FACES = "MULTIPLE_FACES"
    LOW_LIGHT = "LOW_LIGHT"
    INVALID_FRAME = "INVALID_FRAME"
    NOT_READY = "NOT_READY"


class ModelInfo(BaseModel):
    name: str
    version: str
    checkpointSha256: str | None = None
    preprocessingMode: str | None = None
    preprocessingVersion: str | None = None
    pipelineVersion: str | None = None


class PredictionResponse(BaseModel):
    schemaVersion: str = "1.0"
    frameId: str | None = None
    status: PipelineStatus
    personId: str | None = None
    similarity: float | None = None
    model: ModelInfo
    processingMs: float


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    schemaVersion: str = "1.0"
    error: ErrorDetail
