from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from pathlib import Path

import numpy as np

from app.face_matcher import l2_normalize

PERSON_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


class FaceDatabase:
    def __init__(self, path: str | Path, model_version: str, embedding_dim: int = 128,
                 max_samples_per_person: int = 20):
        self.path = Path(path)
        self.model_version = model_version
        self.embedding_dim = embedding_dim
        self.max_samples = max_samples_per_person
        self._lock = threading.RLock()
        self._data = self._load()

    def _empty(self) -> dict:
        return {"schemaVersion": "1.0", "modelVersion": self.model_version,
                "embeddingDim": self.embedding_dim, "persons": {}}

    def _load(self) -> dict:
        if not self.path.exists():
            return self._empty()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if data.get("modelVersion") != self.model_version or data.get("embeddingDim") != self.embedding_dim:
                raise ValueError("Face database model version or embedding dimension mismatch")
            if not isinstance(data.get("persons"), dict):
                raise ValueError("Face database persons field is invalid")
            for person_id, samples in data["persons"].items():
                if not PERSON_ID_RE.fullmatch(person_id) or not isinstance(samples, list):
                    raise ValueError("Face database contains invalid person data")
                for sample in samples:
                    vector = np.asarray(sample, dtype=np.float32)
                    if vector.shape != (self.embedding_dim,) or not np.isfinite(vector).all():
                        raise ValueError("Face database contains an invalid embedding")
            return data
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            raise ValueError(f"Could not load face database: {self.path}") from exc

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=self.path.name, suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(self._data, handle, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, self.path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

    def enroll(self, person_id: str, embedding: np.ndarray) -> int:
        if not PERSON_ID_RE.fullmatch(person_id):
            raise ValueError("personId must be 1-64 safe identifier characters")
        vector = l2_normalize(embedding)
        if vector.shape != (self.embedding_dim,):
            raise ValueError("Embedding dimension mismatch")
        with self._lock:
            samples = self._data["persons"].setdefault(person_id, [])
            if len(samples) >= self.max_samples:
                raise ValueError("Maximum samples reached for this person")
            samples.append(vector.tolist())
            self._save()
            return len(samples)

    def delete(self, person_id: str) -> bool:
        with self._lock:
            existed = self._data["persons"].pop(person_id, None) is not None
            if existed:
                self._save()
            return existed

    def list_persons(self) -> list[dict]:
        with self._lock:
            return [{"personId": key, "sampleCount": len(value)}
                    for key, value in sorted(self._data["persons"].items())]

    def candidates(self) -> list[tuple[str, np.ndarray]]:
        with self._lock:
            return [(person_id, np.asarray(sample, dtype=np.float32))
                    for person_id, samples in self._data["persons"].items() for sample in samples]
