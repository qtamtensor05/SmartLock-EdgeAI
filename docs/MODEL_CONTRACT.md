# Model contract

## MobileFaceNet

- File: `models/mobilefacenet_scripted.pt`
- SHA-256 đã kiểm tra: `780E31E7C2639A0D5FDEBE843F5DF3FF81FDA79A090164DF0FF40514D172853A`
- Loader: `torch.jit.load(..., map_location="cpu")`, sau đó `eval()`.
- Inference: `torch.inference_mode()`.
- Input: RGB, float32, NCHW `[1, 3, 112, 112]`.
- Output thực tế đã kiểm tra: float32 `[1, 128]`, hữu hạn; code trả cả embedding thô nội bộ và bản L2-normalized.
- Tên/version ứng dụng: `MobileFaceNet` / `fp32-v1`.

Không có bằng chứng kèm checkpoint cho biết dữ liệu huấn luyện đã dùng normalization nào. Cấu hình hiện tại dùng `(pixel / 255 - 0.5) / 0.5`, tương đương gần đúng miền `[-1, 1]`, và đánh dấu `verified_against_training: false`. Phải xác minh với tác giả/export pipeline hoặc tập validation trước khi chốt.

## Detection và alignment

YuNet `face_detection_yunet_2023mar.onnx` từ OpenCV Zoo, SHA-256 `8F2383E4DD3CFBB4553EA8718107FC0423210DC964F9F4280604804ED2552FA4`. Output mỗi mặt gồm bbox `(x, y, width, height)`, confidence và 5 landmarks theo pixel trên ảnh gốc: mắt phải/trái theo thứ tự output model, mũi, hai khóe miệng. Code không tự tạo landmark.

Alignment dùng `estimateAffinePartial2D` với 5 điểm và template ArcFace 112×112 trong `config/model_config.yaml`, sau đó `warpAffine` linear. Không resize toàn frame.

## Quy tắc tương thích

Database lưu `modelVersion` và `embeddingDim`; khác version/dimension thì từ chối load. Đổi normalization, alignment template hoặc checkpoint phải tạo version embedding mới và đăng ký lại. Threshold cosine `0.65` chỉ là giá trị cấu hình ban đầu, **chưa hiệu chuẩn** và similarity không phải xác suất.
