import os
from contextlib import asynccontextmanager

import numpy as np
from fastapi.testclient import TestClient

from app.face_pipeline import PipelineResult
from app.main import app
from app.schemas import PipelineStatus


class Database:
    def list_persons(self): return []
    def delete(self, _): return False


class Pipeline:
    database = Database()
    def process(self, _payload, include_embedding=False):
        return PipelineResult(PipelineStatus.UNKNOWN, 12.3,
                              embedding=np.ones(128) if include_embedding else None)


@asynccontextmanager
async def fake_lifespan(application):
    application.state.config = {"transport": {"max_jpeg_bytes": 1_048_576, "request_timeout_seconds": 1},
                                "model": {"name": "MobileFaceNet", "version": "fp32-v1"}}
    application.state.pipeline = Pipeline()
    application.state.startup_error = None
    yield


def test_predict_raw_jpeg_schema():
    original = app.router.lifespan_context
    app.router.lifespan_context = fake_lifespan
    try:
        with TestClient(app) as client:
            response = client.post("/predict", content=b"jpeg", headers={"Content-Type": "image/jpeg", "X-Frame-Id": "f-1"})
        assert response.status_code == 200
        assert response.json()["frameId"] == "f-1"
        assert response.json()["status"] == "UNKNOWN"
        assert "embedding" not in response.json()
    finally:
        app.router.lifespan_context = original


def test_admin_endpoint_is_closed_without_key():
    original = app.router.lifespan_context
    app.router.lifespan_context = fake_lifespan
    os.environ.pop("SMARTLOCK_ADMIN_API_KEY", None)
    try:
        with TestClient(app) as client:
            response = client.get("/persons")
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "UNAUTHORIZED"
    finally:
        app.router.lifespan_context = original
