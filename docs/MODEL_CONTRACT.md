# Model contract

## Checkpoint audit

- File: `models/mobilefacenet_scripted.pt`
- Size: 7,607,970 bytes.
- SHA-256: `780e31e7c2639a0d5fdebe843f5df3ff81fda79a090164df0ff40514d172853a`.
- Source comparison: exact size and SHA-256 match with `pretrained_model/mobilefacenet_scripted.pt` in `foamliu/MobileFaceNet`, commit `a6cc9032a659b615f477833e1a70b5e7931bcccc`.
- Artifact ID: `mobilefacenet-fp32-v1`; backward-compatible API/database model version: `fp32-v1`.
- Load contract: `torch.jit.load(..., map_location="cpu")`, `eval()`, `torch.inference_mode()`.
- Verified runtime contract: input float32 `[1,3,112,112]`; output float32 `[1,128]`; no NaN/Inf.
- Graph audit: the first tensor operation is `conv2d`; graph has no input `div` or `permute`. Pixel normalization and RGB-to-NCHW conversion are not embedded in TorchScript.

Checkpoint identity is **VERIFIED_FROM_SOURCE** against that repository snapshot. The training-run provenance that produced the packaged checkpoint is not documented sufficiently to bind one normalization mode conclusively, so preprocessing remains **PENDING_VERIFICATION**.

## Source traceability

| Component | Source evidence at commit `a6cc903` | Conclusion |
|---|---|---|
| Input shape | `mobilefacenet.py` scopes `(3,112,112)`; TorchScript runtime accepts `[1,3,112,112]` | Verified |
| RGB/BGR | `data_gen.py` and `custom_data_gen.py` call PIL `.convert('RGB')`; `lfw_eval.py` explicitly converts aligned BGR to RGB | Verified |
| Normalization | Training/validation generators use ImageNet values; `demo.py` selects mean/std 0.5 and separately prints ArcFace-128-like values | Conflicting source; checkpoint binding unknown |
| Alignment | `facenet_utils.py` reads BGR, builds a padded square 112 reference, then calls similarity warp | Verified source behavior; differs from current pipeline template |
| Resize/output | Source config is 112x112; alignment uses `cv2.warpAffine` | Verified |
| Export | `export.py` scripts the network module only; no transform is embedded | Verified |
| Checkpoint identity | Exact 7,607,970-byte SHA-256 match | Verified |

## Normalization modes

The active default remains `current`; `verified_against_training` remains `false`.

| Mode | Version | Formula | p=0 | p=127 | p=128 | p=255 | Status |
|---|---|---|---:|---:|---:|---:|---|
| current | `preprocess-rgb-mean05-v1` | `(p/255-0.5)/0.5` | -1 | -0.003922 | 0.003922 | 1 | PENDING_VERIFICATION |
| imagenet | `preprocess-rgb-imagenet-v1` | `(p/255-mean)/std` | channel-dependent | channel-dependent | channel-dependent | channel-dependent | PENDING_VERIFICATION |
| arcface128 | `preprocess-rgb-arcface128-v1` | `(p-127.5)/128` | -0.996094 | -0.003906 | 0.003906 | 0.996094 | PENDING_VERIFICATION |

ImageNet channel boundaries `(R,G,B)`:

- p=0: `(-2.117904, -2.035714, -1.804444)`
- p=127: `(0.056940, 0.187675, 0.409063)`
- p=128: `(0.074065, 0.205182, 0.426492)`
- p=255: `(2.248908, 2.428571, 2.640000)`

All modes accept only RGB `uint8` 112x112, return float32 NCHW `[1,3,112,112]`, and reject float input to prevent accidental double normalization.

## Alignment contract

Current Edge AI order follows YuNet: right eye, left eye, nose, right mouth corner, left mouth corner, expressed as pixel `(x,y)` on the original image. Output is RGB 112x112 using `estimateAffinePartial2D` and linear `warpAffine`.

The current template is the common square ArcFace template:

`[(38.2946,51.6963), (73.5318,51.5014), (56.0252,71.7366), (41.5493,92.3655), (70.7299,92.2041)]`.

The source evaluation pipeline applies `default_square=True`, `inner_padding_factor=0.25`, then scales to 112x112, yielding a materially tighter/different reference (approximately `[(44.1964,53.1309), (67.6879,53.0009), (56.0168,66.4911), (46.3662,80.2437), (65.8199,80.1361)]`). It processes BGR through alignment and converts to RGB afterward. The Edge AI template is intentionally unchanged until controlled comparison data exists.

## Pipeline/database compatibility

The pipeline identifier is a SHA-256-derived ID over checkpoint hash, preprocessing version, RGB order, alignment template name and 112x112 input size. New databases store `pipelineVersion`. A mismatching pipeline is rejected; embeddings are never mixed. A legacy database without `pipelineVersion` is accepted only for the unchanged `current` default, then receives the version metadata on its next atomic write. No database is deleted automatically.

Changing normalization, checkpoint or alignment requires a new pipeline version and re-enrollment or a separately validated migration. Cosine threshold `0.65` remains uncalibrated.
