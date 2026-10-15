from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from itertools import combinations
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import load_config, resolve_path
from app.face_alignment import align_face
from app.face_detector import YuNetFaceDetector
from app.jpeg_decoder import JPEGDecoder
from app.mobilefacenet import MobileFaceNet
from app.preprocessing import FacePreprocessor, NORMALIZATION_MODES

IMAGE_SUFFIXES = {".jpg", ".jpeg"}


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.clip(np.dot(a, b), -1.0, 1.0))


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare preprocessing modes on the same aligned faces")
    parser.add_argument("images", type=Path, help="Directory of permitted JPEG images")
    parser.add_argument("--output-dir", type=Path, default=Path("validation_results"))
    args = parser.parse_args()
    if not args.images.is_dir():
        raise SystemExit(f"Image directory not found: {args.images}")

    config = load_config()
    model_path = resolve_path(config["model"]["path"])
    checkpoint_hash = hashlib.sha256(model_path.read_bytes()).hexdigest()
    expected_hash = config["model"]["checkpoint_sha256"].lower()
    if checkpoint_hash != expected_hash:
        raise SystemExit("Checkpoint SHA-256 does not match configuration")

    detector_config = config["detector"]
    detector = YuNetFaceDetector(resolve_path(detector_config["model_path"]),
                                 detector_config["confidence_threshold"],
                                 detector_config["nms_threshold"], detector_config["top_k"])
    decoder = JPEGDecoder(config["transport"]["max_jpeg_bytes"],
                          config["transport"]["max_decoded_pixels"])
    model = MobileFaceNet(model_path, config["model"]["embedding_dim"],
                          config["model"]["device"], expected_hash)
    preprocessors = {mode: FacePreprocessor(config["input"], mode) for mode in sorted(NORMALIZATION_MODES)}

    # Cache only aligned RGB arrays in memory. No face crops or embeddings are written.
    aligned_cache: dict[str, np.ndarray] = {}
    failures: list[dict[str, str]] = []
    for path in sorted(p for p in args.images.rglob("*") if p.suffix.lower() in IMAGE_SUFFIXES):
        relative = path.relative_to(args.images).as_posix()
        try:
            frame = decoder.decode(path.read_bytes())
            detections = detector.detect(frame.rgb)
            if len(detections) != 1:
                raise ValueError(f"expected exactly one face, detected {len(detections)}")
            aligned_cache[relative] = align_face(frame.rgb, detections[0].landmarks)
        except Exception as exc:
            failures.append({"image": relative, "error": f"{type(exc).__name__}: {exc}"})

    embeddings: dict[tuple[str, str], np.ndarray] = {}
    for image_name, aligned in aligned_cache.items():
        for mode, preprocessor in preprocessors.items():
            embeddings[(image_name, mode)] = model.embed(preprocessor(aligned)).normalized

    rows: list[dict[str, object]] = []
    for image_name in aligned_cache:
        for mode_a, mode_b in combinations(sorted(preprocessors), 2):
            rows.append({"image": image_name, "modeA": mode_a, "modeB": mode_b,
                         "cosineSimilarity": cosine(embeddings[(image_name, mode_a)],
                                                      embeddings[(image_name, mode_b)])})

    args.output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = args.output_dir / "preprocessing_comparison.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["image", "modeA", "modeB", "cosineSimilarity"])
        writer.writeheader()
        writer.writerows(rows)

    mode_metadata = {mode: processor.metadata for mode, processor in preprocessors.items()}
    summary = {
        "schemaVersion": "1.0",
        "status": "UNLABELED_INFERENCE_ONLY",
        "checkpoint": {"path": str(config["model"]["path"]), "sha256": checkpoint_hash,
                       "modelVersion": config["model"]["version"],
                       "artifactId": config["model"]["artifact_id"]},
        "alignment": config["alignment"],
        "preprocessing": mode_metadata,
        "images": {"discovered": len(aligned_cache) + len(failures),
                   "aligned": len(aligned_cache), "failed": len(failures)},
        "crossModeCosine": rows,
        "failures": failures,
        "accuracyMetrics": None,
        "note": "No identities or embeddings are written; FAR/FRR require labeled validation and independent test sets.",
    }
    json_path = args.output_dir / "preprocessing_comparison.json"
    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"aligned={len(aligned_cache)} failed={len(failures)} csv={csv_path} json={json_path}")


if __name__ == "__main__":
    main()
