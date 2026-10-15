# Báo cáo Giai đoạn 1 — 2026-10-15

## Phase 1 Acceptance - Preprocessing Verification (2026-10-16)

### Thay đổi và bằng chứng

- Đối chiếu repository `foamliu/MobileFaceNet` tại commit `a6cc9032a659b615f477833e1a70b5e7931bcccc`.
- Checkpoint nguồn và workspace cùng 7,607,970 byte, SHA-256 `780e31e7c2639a0d5fdebe843f5df3ff81fda79a090164df0ff40514d172853a`.
- TorchScript thực tế: input `[1,3,112,112]` float32, output `[1,128]` float32 hữu hạn. Graph bắt đầu bằng convolution, không chứa input division/permutation; preprocessing không nằm trong model.
- Source training/validation dùng ImageNet normalization và RGB. `demo.py` lại chọn mean/std 0.5 và chỉ dùng ArcFace-128-like formula để in so sánh. Không có metadata training-run đủ mạnh để gắn chắc packaged checkpoint với một mode.
- Source alignment dùng padded square reference khác template Edge AI hiện tại. Template đang dùng không bị thay đổi âm thầm.
- Bổ sung ba mode/version, pipeline fingerprint, chống trộn database và công cụ so sánh CSV/JSON không ghi ảnh/embedding.

### Kết quả thực nghiệm không nhãn

Trên cùng một crop từ một ảnh mẫu OpenCV: arcface128/current `0.999998`; arcface128/imagenet `0.947641`; current/imagenet `0.948107`. Đây chỉ là cosine chéo mode, không phải accuracy. Không tính FAR/FRR/ROC/TAR và không chọn mode tốt nhất.

### Kết luận nghiệm thu

Trạng thái cuối: **PENDING_VERIFICATION**. Công cụ kỹ thuật và kiểm soát version đã hoàn thiện; mode mặc định vẫn là `current`, `verified_against_training: false`, threshold 0.65 vẫn chưa hiệu chuẩn. Muốn PASS cần bằng chứng preprocessing gắn trực tiếp với checkpoint hoặc dataset có nhãn/đồng thuận với validation và test độc lập theo `PREPROCESSING_VALIDATION.md`.

## Yêu cầu — Kết quả

- Pipeline độc lập: đã triển khai decoder, YuNet 5 landmarks, alignment, preprocessing cấu hình, MobileFaceNet, matcher 1:N và database.
- Tình huống biên: đã xử lý frame lỗi, rỗng/quá 1 MiB, pixel limit, thiếu sáng, 0/1/nhiều mặt và model lỗi theo hướng fail-closed.
- API: đã có 5 endpoint; `/predict` nhận raw JPEG; endpoint quản trị yêu cầu API key; không điều khiển khóa.
- Lưu trữ: JSON prototype ghi bằng temp file + `os.replace`, hỗ trợ 20 mẫu/người mặc định, khóa model version/dimension, không lưu ảnh và không log embedding.

## Kiểm chứng đã thực sự chạy

Môi trường: Windows, Python 3.14.7, Torch 2.14.1 CPU, OpenCV 4.14.0.94.

- `python scripts/inspect_model.py`: nạp model thành công; input `[1,3,112,112]` float32; output `[1,128]` float32; finite = true.
- `python scripts/test_inference.py`: embedding raw `(128,)`, L2 sau chuẩn hóa = `1.000000`; một lần đo inference 581.003 ms.
- YuNet smoke test trên ảnh đen 160×120: chạy thành công và trả 0 mặt.
- `pytest -q`: **20 passed**, 2 warning, 31.62 giây.
- Benchmark 1 vòng trên ảnh `lena.jpg` công khai của OpenCV (smoke, không phải accuracy): decode 49.547 ms; detect 58.575 ms; align 0.713 ms; preprocess 1.004 ms; inference 542.034 ms; match 0.016 ms; total 651.963 ms.

Các số latency trên chỉ là một lần đo cold/smoke trên máy phát triển, không phải benchmark thống kê hay ESP32.

## Chưa hoàn thành/chưa xác minh

- Chưa có dữ liệu nhiều danh tính được phép sử dụng: chưa đo genuine/impostor, FAR, FRR hoặc accuracy; threshold 0.65 chưa hiệu chuẩn.
- Normalization của model lúc huấn luyện chưa được xác minh.
- Chưa nghiệm thu detector/recognition bằng ảnh thật từ OV2640 qua gateway tại 160×120 và 320×240.
- `camera-model-input-contract.md` không có trong workspace; triển khai dựa trên contract được cung cấp trong yêu cầu.
- Python 3.14 sinh cảnh báo từ PyTorch rằng `torch.jit.load` chưa được hỗ trợ chính thức; nên xác nhận lại trên Python 3.12/3.13 cho runtime triển khai.
- JSON chứa dữ liệu sinh trắc chưa mã hóa at-rest. API key đơn lẻ chỉ phù hợp prototype; chưa có TLS, rate limit, audit, rotation hay phân quyền danh tính.
- Timeout HTTP dừng chờ response nhưng thread CPU đang chạy không thể bị hủy cưỡng bức; production cần process isolation/worker limits.

## Điều kiện sang Giai đoạn 2

1. Xác minh preprocessing từ nguồn export/training hoặc validation có kiểm soát.
2. Thu thập dataset có đồng thuận từ camera đích, tách enrollment/evaluation và hiệu chuẩn threshold theo FAR/FRR mục tiêu.
3. Chạy benchmark nhiều vòng/warm-up trên phần cứng triển khai và đặt SLO latency.
4. Hoàn thiện bảo vệ dữ liệu sinh trắc và authentication/authorization production.
5. Chỉ sau khi FP32 baseline được khóa mới đánh giá ONNX/INT8; so sánh embedding/accuracy, không dùng Test/production data để chọn mô hình.
