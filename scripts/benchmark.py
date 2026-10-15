from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import load_config
from app.main import build_pipeline


def timed(fn, *args):
    started = time.perf_counter()
    value = fn(*args)
    return value, (time.perf_counter() - started) * 1000


def main():
    parser = argparse.ArgumentParser(description="Benchmark one permitted JPEG; does not measure accuracy")
    parser.add_argument("jpeg", type=Path)
    parser.add_argument("--iterations", type=int, default=10)
    args = parser.parse_args()
    config, rows = load_config(), []
    pipeline = build_pipeline(config)
    payload = args.jpeg.read_bytes()
    for _ in range(args.iterations):
        total_start = time.perf_counter()
        frame, decode_ms = timed(pipeline.decoder.decode, payload)
        detections, detection_ms = timed(pipeline.detector.detect, frame.rgb)
        if len(detections) != 1:
            raise SystemExit(f"Benchmark requires exactly one face; detected {len(detections)}")
        from app.face_alignment import align_face
        aligned, alignment_ms = timed(align_face, frame.rgb, detections[0].landmarks)
        tensor, preprocessing_ms = timed(pipeline.preprocessor, aligned)
        embedded, inference_ms = timed(pipeline.embedder.embed, tensor)
        _, matching_ms = timed(pipeline.matcher.match, embedded.normalized, pipeline.database.candidates())
        rows.append({"decodeMs": decode_ms, "detectionMs": detection_ms, "alignmentMs": alignment_ms,
                     "preprocessingMs": preprocessing_ms, "inferenceMs": inference_ms,
                     "matchingMs": matching_ms, "totalMs": (time.perf_counter() - total_start) * 1000})
    summary = {key: sum(row[key] for row in rows) / len(rows) for key in rows[0]}
    print(json.dumps({"iterations": len(rows), "mean": summary,
                      "accuracyEvaluated": False}, indent=2))


if __name__ == "__main__":
    main()
