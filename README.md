# SmartLock Edge AI

Nhận diện khuôn mặt chạy trực tiếp trên ESP32-S3 cho SmartLock. Repo này là submodule
`edge-ai/` của SmartLock và chỉ chứa component ESP-IDF
[`face-edge/components/face_auth`](face-edge/components/face_auth/README.md):

```text
JPEG từ camera → MSRMNP (tìm mặt + 5 điểm mốc) → căn chỉnh 112×112
→ MobileFaceNet int8 (embedding) → cosine với mẫu lưu trong NVS → MATCH / NO_MATCH / ...
```

Component không điều khiển khóa; firmware SmartLock (`LockController`) quyết định
mở cửa. Cách build, cấu hình và luồng thẻ → mặt → OTP: xem README của SmartLock và
[face-edge/README.md](face-edge/README.md).

Phần thử nghiệm cũ (dịch vụ Python trên PC, probe QEMU, firmware UART thử, mô phỏng)
đã được gỡ; lấy lại từ tag `archive/phase1-experiments`.
