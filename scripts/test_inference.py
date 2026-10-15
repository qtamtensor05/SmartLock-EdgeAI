import time
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.mobilefacenet import MobileFaceNet


def main():
    model = MobileFaceNet("models/mobilefacenet_scripted.pt")
    tensor = torch.zeros((1, 3, 112, 112), dtype=torch.float32)
    started = time.perf_counter()
    result = model.embed(tensor)
    print(f"inference_ms={(time.perf_counter() - started) * 1000:.3f}")
    print(f"raw_shape={result.raw.shape} normalized_l2={np.linalg.norm(result.normalized):.6f}")


if __name__ == "__main__":
    main()
