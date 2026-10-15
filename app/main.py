from __future__ import annotations

import asyncio
import hmac
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import load_config, resolve_path
from app.face_database import FaceDatabase
from app.face_detector import YuNetFaceDetector
from app.face_matcher import FaceMatcher
from app.face_pipeline import FacePipeline
from app.jpeg_decoder import JPEGDecoder
from app.mobilefacenet import MobileFaceNet
from app.preprocessing import FacePreprocessor
from app.schemas import ErrorDetail, ErrorResponse, ModelInfo, PredictionResponse


def error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content=ErrorResponse(
        error=ErrorDetail(code=code, message=message)).model_dump())


def build_pipeline(config: dict) -> FacePipeline:
    database_path = os.getenv("SMARTLOCK_DATABASE_PATH", config["storage"]["path"])
    database = FaceDatabase(resolve_path(database_path), config["model"]["version"],
                            config["model"]["embedding_dim"],
                            config["storage"]["max_samples_per_person"])
    return FacePipeline(
        JPEGDecoder(config["transport"]["max_jpeg_bytes"], config["transport"]["max_decoded_pixels"]),
        YuNetFaceDetector(resolve_path(config["detector"]["model_path"]),
                          config["detector"]["confidence_threshold"],
                          config["detector"]["nms_threshold"], config["detector"]["top_k"]),
        FacePreprocessor(config["input"]),
        MobileFaceNet(resolve_path(config["model"]["path"]),
                      config["model"]["embedding_dim"], config["model"]["device"]),
        FaceMatcher(config["matching"]["cosine_threshold"]), database,
        config["quality"]["low_light_mean_luma"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.config = load_config()
    try:
        app.state.pipeline = build_pipeline(app.state.config)
        app.state.startup_error = None
    except Exception as exc:
        app.state.pipeline = None
        app.state.startup_error = f"{type(exc).__name__}: {exc}"
    yield


app = FastAPI(title="SmartLock Edge AI", version="1.0.0", lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def validation_handler(_request, exc):
    return error(422, "VALIDATION_ERROR", str(exc))


@app.exception_handler(HTTPException)
async def http_error_handler(_request, exc: HTTPException):
    if isinstance(exc.detail, dict):
        return error(exc.status_code, exc.detail.get("code", "HTTP_ERROR"), exc.detail.get("message", "Request failed"))
    return error(exc.status_code, "HTTP_ERROR", str(exc.detail))


def require_admin(x_admin_key: str | None = Header(default=None)) -> None:
    expected = os.getenv("SMARTLOCK_ADMIN_API_KEY")
    if not expected or not x_admin_key or not hmac.compare_digest(x_admin_key, expected):
        raise HTTPException(401, {"code": "UNAUTHORIZED", "message": "Valid X-Admin-Key required"})


def ready_pipeline(request: Request) -> FacePipeline:
    if request.app.state.pipeline is None:
        raise HTTPException(503, {"code": "NOT_READY", "message": "AI pipeline is not ready"})
    return request.app.state.pipeline


async def jpeg_body(request: Request) -> bytes:
    config = request.app.state.config
    limit = config["transport"]["max_jpeg_bytes"]
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "image/jpeg":
        raise HTTPException(415, {"code": "UNSUPPORTED_MEDIA_TYPE", "message": "Content-Type must be image/jpeg"})
    length = request.headers.get("content-length")
    if length:
        try:
            if int(length) > limit:
                raise HTTPException(413, {"code": "PAYLOAD_TOO_LARGE", "message": "JPEG exceeds 1 MiB"})
        except ValueError:
            raise HTTPException(400, {"code": "INVALID_CONTENT_LENGTH", "message": "Invalid Content-Length"})
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > limit:
            raise HTTPException(413, {"code": "PAYLOAD_TOO_LARGE", "message": "JPEG exceeds 1 MiB"})
    return bytes(body)


@app.get("/health")
async def health(request: Request):
    ready = request.app.state.pipeline is not None
    return {"schemaVersion": "1.0", "status": "ready" if ready else "not_ready",
            "detail": None if ready else request.app.state.startup_error}


@app.post("/predict", response_model=PredictionResponse)
async def predict(request: Request, frame_id: str | None = Header(default=None, alias="X-Frame-Id"),
                  pipeline: FacePipeline = Depends(ready_pipeline)):
    payload = await jpeg_body(request)
    timeout = request.app.state.config["transport"]["request_timeout_seconds"]
    try:
        result = await asyncio.wait_for(asyncio.to_thread(pipeline.process, payload), timeout)
    except TimeoutError:
        return error(504, "PROCESSING_TIMEOUT", "Frame processing timed out")
    model = request.app.state.config["model"]
    return PredictionResponse(frameId=frame_id, status=result.status, personId=result.person_id,
                              similarity=result.similarity, model=ModelInfo(name=model["name"], version=model["version"]),
                              processingMs=round(result.processing_ms, 3))


@app.post("/enroll", response_model=dict, dependencies=[Depends(require_admin)])
async def enroll(request: Request, person_id: str = Header(alias="X-Person-Id"),
                 pipeline: FacePipeline = Depends(ready_pipeline)):
    payload = await jpeg_body(request)
    timeout = request.app.state.config["transport"]["request_timeout_seconds"]
    try:
        result = await asyncio.wait_for(asyncio.to_thread(pipeline.process, payload, True), timeout)
    except TimeoutError:
        return error(504, "PROCESSING_TIMEOUT", "Enrollment processing timed out")
    if result.status.value not in {"UNKNOWN", "MATCHED"} or result.embedding is None:
        return error(422, result.status.value, "Exactly one usable face is required for enrollment")
    try:
        count = pipeline.database.enroll(person_id, result.embedding)
    except ValueError as exc:
        return error(409, "ENROLLMENT_REJECTED", str(exc))
    return {"schemaVersion": "1.0", "personId": person_id, "sampleCount": count}


@app.get("/persons", dependencies=[Depends(require_admin)])
async def persons(pipeline: FacePipeline = Depends(ready_pipeline)):
    return {"schemaVersion": "1.0", "persons": pipeline.database.list_persons()}


@app.delete("/persons/{person_id}", dependencies=[Depends(require_admin)])
async def delete_person(person_id: str, pipeline: FacePipeline = Depends(ready_pipeline)):
    if not pipeline.database.delete(person_id):
        return error(404, "PERSON_NOT_FOUND", "personId is not enrolled")
    return Response(status_code=204)
