# Face edge — AI khuôn mặt chạy trên ESP32-S3

Chứa component ESP-IDF [`components/face_auth`](components/face_auth/README.md) mà
firmware khóa SmartLock link vào (luồng thẻ → mặt → OTP). Component dùng model int8
của Espressif, tải theo phiên bản ghim trong `dependencies.lock` của SmartLock:

| Model | Việc | Component |
| --- | --- | --- |
| `human_face_detect_msr_s8_v1` + `..._mnp_s8_v1` (MSRMNP) | Tìm mặt + 5 điểm mốc | `espressif/human_face_detect` 0.5.2 |
| `human_face_feat_mfn_s8_v1` (MobileFaceNet) | Tạo embedding khuôn mặt | `espressif/human_face_recognition` 0.3.3 |

Model được đóng gói vào flash rodata của firmware khi build; không có file model nào
trong repo này.

## Tích hợp trong SmartLock

Firmware khóa (ESP-IDF 5.5.2 + Arduino component) sở hữu camera và gọi
`face_auth` qua `src/face/FaceService.cpp`:

1. Thẻ hợp lệ theo server → `FaceVerifyState`: camera stream xem trước, người dùng
   chụp bằng `#` hoặc nút web; khung đó được so 1:1 với các mẫu đã đăng ký cho UID
   thẻ. Đúng → bước OTP; không có mẫu, nhiều mặt, 3 lần không khớp, lỗi model hoặc
   hết thời gian → từ chối (fail closed).
2. Đăng ký (mật khẩu master → OTP → quẹt thẻ) → `FaceEnrollState` lưu 3 mẫu
   (nhìn thẳng, hơi trái, hơi phải) vào phân vùng `face_live`, namespace `mfn_s8_uid1`.
3. Component chỉ trả trạng thái và điểm; `LockController` quyết định mở khóa.

Đã kiểm chứng trên mạch thật (2026-11-27): đăng ký 3 mẫu, rồi thẻ → mặt (điểm
0,81–0,86, khoảng 0,6–0,7 s mỗi lần) → OTP → mở khóa; thẻ chưa đăng ký mặt bị từ chối.
Hai điều kiện để detector thấy mặt: ảnh phải đúng chiều (camera trên mạch thử lắp
ngược, firmware lật 180°) và thấy trọn đầu ở khoảng 40–60 cm.

`face_models.compile_req.yml` khai báo toán tử/kernel model cần với ESP-DL. Bắt buộc
khi build chung với component khác cũng đăng ký danh sách (ESP-SR qua Arduino), nếu
không ESP-DL bỏ `Concat` và model báo `Do not support Concat`.

Thử trên bàn không cần server: `tools/bench_server.py` của SmartLock (trang xem trước
camera, nút chụp, OTP giả lập).

## Phần thử nghiệm đã gỡ

Các phần dưới đây phục vụ giai đoạn thử nghiệm và không còn được firmware dùng; đã
gỡ khỏi nhánh chính, vẫn lấy lại được từ tag `archive/phase1-experiments` (commit
`f700282`):

- Dịch vụ Python trên PC (`app/`, `tests/`, `scripts/`, `config/`, `docs/`): FastAPI
  + YuNet + MobileFaceNet FP32 (`models/mobilefacenet_scripted.pt`).
- `examples/esp32s3_probe` + `tools/*qemu*`, `tools/probe.py`: thử model trên ảnh
  nhúng cố định và QEMU.
- `examples/esp32s3_live` + `tools/live_camera*.py`: firmware UART độc lập để đăng ký/
  nhận diện thử; thay bằng firmware khóa + `tools/bench_server.py`.
- `simulate.py`: mô phỏng đối sánh bằng vector nhân tạo.

```powershell
git show archive/phase1-experiments:face-edge/README.md
git checkout archive/phase1-experiments -- face-edge/examples/esp32s3_live
```

## Tài liệu

- https://github.com/espressif/esp-who
- https://github.com/espressif/esp-dl
