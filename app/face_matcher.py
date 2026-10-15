from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def l2_normalize(embedding: np.ndarray) -> np.ndarray:
    vector = np.asarray(embedding, dtype=np.float32)
    if vector.ndim != 1 or not np.isfinite(vector).all():
        raise ValueError("Embedding must be a finite one-dimensional vector")
    norm = float(np.linalg.norm(vector))
    if norm <= 1e-12:
        raise ValueError("Cannot normalize a zero embedding")
    return vector / norm


def cosine_similarity(left: np.ndarray, right: np.ndarray) -> float:
    a, b = l2_normalize(left), l2_normalize(right)
    if a.shape != b.shape:
        raise ValueError("Embedding dimensions do not match")
    return float(np.clip(np.dot(a, b), -1.0, 1.0))


@dataclass(frozen=True)
class MatchResult:
    person_id: str | None
    similarity: float | None
    matched: bool


class FaceMatcher:
    def __init__(self, threshold: float):
        if not -1.0 <= threshold <= 1.0:
            raise ValueError("Cosine threshold must be between -1 and 1")
        self.threshold = threshold

    def match(self, query: np.ndarray, candidates: list[tuple[str, np.ndarray]]) -> MatchResult:
        best_id, best_score = None, None
        for person_id, embedding in candidates:
            score = cosine_similarity(query, embedding)
            if best_score is None or score > best_score:
                best_id, best_score = person_id, score
        return MatchResult(best_id if best_score is not None and best_score >= self.threshold else None,
                           best_score, bool(best_score is not None and best_score >= self.threshold))
