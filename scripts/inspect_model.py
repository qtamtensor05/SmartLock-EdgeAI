from pathlib import Path

import torch


def main():
    path = Path("models/mobilefacenet_scripted.pt")
    model = torch.jit.load(str(path), map_location="cpu").eval()
    sample = torch.zeros((1, 3, 112, 112), dtype=torch.float32)
    with torch.inference_mode():
        output = model(sample)
    print(f"path={path} input={tuple(sample.shape)} input_dtype={sample.dtype}")
    print(f"output={tuple(output.shape)} output_dtype={output.dtype} finite={bool(torch.isfinite(output).all())}")


if __name__ == "__main__":
    main()
