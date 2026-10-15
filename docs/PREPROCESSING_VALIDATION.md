# Preprocessing validation

## Current acceptance status

**PENDING_VERIFICATION** — source and graph auditing are complete, but there is no consented labeled validation/test dataset tying recognition accuracy to a preprocessing mode.

- `VERIFIED_FROM_SOURCE`: exact checkpoint provenance and its preprocessing are directly established.
- `VALIDATED_EMPIRICALLY`: mode selected on labeled validation data and confirmed on an independent test split.
- `PENDING_VERIFICATION`: evidence is insufficient for either condition above.

## Method

`scripts/compare_preprocessing.py` decodes each permitted JPEG, runs YuNet and alignment once, caches only the aligned RGB array in memory, and sends that identical crop through `current`, `imagenet` and `arcface128`. Each embedding is L2-normalized. CSV/JSON contain only paths, configuration metadata and cosine scores—not face crops or raw embeddings.

```powershell
.\.venv\Scripts\python.exe scripts\compare_preprocessing.py path\to\permitted-jpegs --output-dir validation_results
```

Outputs are `preprocessing_comparison.csv` and `preprocessing_comparison.json` under the selected directory.

## Smoke result on 2026-10-16

One unlabeled OpenCV sample image was detected/aligned successfully:

| Mode pair | Cosine |
|---|---:|
| arcface128/current | 0.999998 |
| arcface128/imagenet | 0.947641 |
| current/imagenet | 0.948107 |

This proves all modes execute and produce different embeddings. One unlabeled image cannot establish recognition quality or choose a winner. FAR, FRR, ROC and TAR were not calculated.

## Dataset and empirical evaluation requirements

Use identities collected with explicit permission from the target OV2640 flow. Keep separate enrollment, validation and final test data, accounting for subject/session leakage. Include 160x120 and 320x240 frames, lighting/pose variation, genuine repeats and sufficient impostor pairs. Do not upload biometric data to external services.

For each fixed mode:

1. Keep detector, alignment, checkpoint and matching code identical.
2. Build genuine/impostor scores on validation.
3. Select threshold only on validation against the target FAR/FRR policy.
4. Freeze mode and threshold.
5. Report ROC, FAR, FRR and TAR at configured FAR on independent test data.
6. Record dataset manifest/hash, consent boundary, code commit, checkpoint hash and full pipeline version.

## PASS/FAIL rule

PASS requires either direct checkpoint-specific source proof (`VERIFIED_FROM_SOURCE`) or a predefined empirical acceptance target met on the independent test set (`VALIDATED_EMPIRICALLY`). Unit tests, graph inspection, high cross-mode cosine or one-image inference are not PASS evidence. Until those conditions are met, the result remains `PENDING_VERIFICATION` and the default mode must not change.
