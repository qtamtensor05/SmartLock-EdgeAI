from pathlib import Path
import hashlib

import torch


def main():
    path = Path("models/mobilefacenet_scripted.pt")
    model = torch.jit.load(str(path), map_location="cpu").eval()
    sample = torch.zeros((1, 3, 112, 112), dtype=torch.float32)
    with torch.inference_mode():
        output = model(sample)
    graph = str(model.inlined_graph)
    print(f"path={path} bytes={path.stat().st_size} sha256={hashlib.sha256(path.read_bytes()).hexdigest()}")
    print(f"input={tuple(sample.shape)} input_dtype={sample.dtype}")
    print(f"output={tuple(output.shape)} output_dtype={output.dtype} finite={bool(torch.isfinite(output).all())}")
    print(f"first_tensor_op={'conv2d' if 'aten::conv2d(%x.1' in graph else 'inspect_manually'}")
    print(f"input_div_ops={graph.count('aten::div')} input_permute_ops={graph.count('aten::permute')}")


if __name__ == "__main__":
    main()
