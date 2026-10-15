# SmartLock Edge AI — Giai đoạn 1

Dịch vụ nhận diện khuôn mặt độc lập cho luồng JPEG từ SmartLock. Giai đoạn này chỉ tạo kết quả AI; **không gửi lệnh mở khóa** và chưa phải hệ thống production.

## Kiến trúc

`raw JPEG -> decode RGB -> YuNet (bbox + 5 landmarks) -> similarity alignment 112x112 -> preprocessing cấu hình -> MobileFaceNet FP32 -> L2 -> cosine 1:N`

Các trạng thái nghiệp vụ: `MATCHED`, `UNKNOWN`, `NO_FACE`, `MULTIPLE_FACES`, `LOW_LIGHT`, `INVALID_FRAME`, `NOT_READY`.

## Cài đặt

Khuyến nghị Python 3.12 hoặc 3.13 trên Windows/Linux. Python 3.14 đã chạy test trong lần bàn giao này nhưng PyTorch phát cảnh báo TorchScript chưa được hỗ trợ chính thức trên Python 3.14+.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Hai model phải tồn tại:

- `models/mobilefacenet_scripted.pt` — model do dự án cung cấp, không tự tải/thay thế.
- `models/face_detection_yunet_2023mar.onnx` — YuNet chính thức từ OpenCV Zoo.

Nếu cần lấy lại YuNet:

```powershell
Invoke-WebRequest -Uri "https://github.com/opencv/opencv_zoo/raw/refs/heads/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx" -OutFile "models/face_detection_yunet_2023mar.onnx"
```

Sao chép `.env.example` thành `.env` hoặc đặt biến môi trường thủ công. Uvicorn không tự đọc `.env` nếu không dùng `--env-file`:

```powershell
$env:SMARTLOCK_ADMIN_API_KEY = "a-long-random-secret"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Gọi API

```powershell
curl.exe -X POST "http://127.0.0.1:8000/predict" -H "Content-Type: image/jpeg" -H "X-Frame-Id: frame-001" --data-binary "@frame.jpg"
curl.exe -X POST "http://127.0.0.1:8000/enroll" -H "Content-Type: image/jpeg" -H "X-Admin-Key: a-long-random-secret" -H "X-Person-Id: user-001" --data-binary "@frame.jpg"
curl.exe "http://127.0.0.1:8000/persons" -H "X-Admin-Key: a-long-random-secret"
curl.exe -X DELETE "http://127.0.0.1:8000/persons/user-001" -H "X-Admin-Key: a-long-random-secret"
```

`/predict` nhận trực tiếp body JPEG, không dùng multipart/Base64. Các endpoint quản trị fail-closed nếu chưa cấu hình `SMARTLOCK_ADMIN_API_KEY`.

## Kiểm tra và benchmark

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts\inspect_model.py
.\.venv\Scripts\python.exe scripts\test_inference.py
.\.venv\Scripts\python.exe scripts\benchmark.py path\to\one-face.jpg --iterations 10
```

Benchmark chỉ đo latency. Không có ảnh được phép sử dụng theo nhiều danh tính nên FAR/FRR và threshold chưa được hiệu chuẩn. Công thức normalization hiện là giả định cấu hình, không phải contract đã xác minh từ quá trình huấn luyện. Xem [model contract](docs/MODEL_CONTRACT.md), [API contract](docs/API_CONTRACT.md) và [báo cáo giai đoạn 1](docs/PHASE1_REPORT.md).
