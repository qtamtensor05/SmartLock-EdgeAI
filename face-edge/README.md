# Face edge — AI khuôn mặt chạy trên ESP32-S3

Repo này là submodule `edge-ai/` của SmartLock.

| Thư mục | Vai trò |
| --- | --- |
| `components/face_auth` | **Component được firmware khóa SmartLock link vào** (luồng thẻ → mặt → OTP). Xem [README](components/face_auth/README.md). |
| `examples/esp32s3_live` | Firmware thử độc lập qua UART + `tools/live_camera*.py`; nạp sẽ thay firmware khóa. |
| `examples/esp32s3_probe` | Bản thử ảnh nhúng cố định, chạy QEMU/mạch thật. |
| `simulate.py` | Mô phỏng logic đối sánh trên PC bằng vector nhân tạo. |

## Chạy trên máy tính

Từ repository SmartLock, dùng Python 3 (không cần cài thư viện):

```powershell
python face-edge/simulate.py
```

Kết quả: `output/report.json`, gồm cấu hình đọc trực tiếp từ dự án và các kịch
bản đối sánh 1:N bằng vector nhân tạo. Chương trình không lấy ảnh, không nhận
diện mặt thật, không điều khiển khóa và không mô phỏng CPU ESP32. Ngưỡng 0.8 và
khoảng cách 0.05 chỉ minh họa logic, không dùng làm ngưỡng mở khóa thực tế.

## Những gì lấy được từ dự án

- Board, framework, flash khai báo, loại PSRAM, baud serial: `platformio.ini`.
- GPIO và xung đột chân: `src/config/PinConfig.h`.
- Định dạng và chế độ frame camera: `src/camera/CameraService.cpp`.
- Chu kỳ preview dự kiến: `src/main.cpp`; đây không phải FPS đo được.
- Tham số OTP: `src/config/AppConfig.h`.
- Linh kiện sơ đồ giả lập: `diagram.json`.

Dung lượng PSRAM thực, heap còn trống, độ trễ suy luận, FPS thực, chất lượng
nhận diện và điện năng chưa xác định. Flash 16 MB là cấu hình, chưa phải số đo.
Không tự suy ra board có PSRAM 8 MB chỉ từ loại OPI hay cờ BOARD_HAS_PSRAM.

## Phạm vi thử không cần board

Xem [hướng dẫn build ESP32-S3 dùng JPEG cố định](examples/esp32s3_probe/README.md)
cho bộ phiên bản, lệnh chuẩn bị/build và giới hạn của số liệu.

Đã có [runner QEMU và báo cáo thực thi](examples/esp32s3_probe/QEMU.md).
Chạy `python face-edge/tools/setup_qemu.py` rồi
`python face-edge/tools/run_qemu.py` từ SmartLock-EdgeAI root khi đã có binary.
Model chạy thật trên emulator, nhưng hiện kiểm tra nhận diện chưa đạt.

1. Bộ thử hiện tại: đăng ký/xóa mẫu và phân loại known/unknown/no-face/nhiều
   mặt/ảnh kém/vector lỗi. Các trạng thái camera là input giả lập.
2. Bước tiếp: chọn, ghim phiên bản ESP-IDF/ESP-DL/model; build chương trình
   probe ESP32-S3 dùng ảnh JPEG cố định nhúng trong firmware, thay nguồn OV2640.
   Kiểm tra compile/link, dung lượng image và phần RAM tĩnh từ ELF/map nếu có
   toolchain. Những số này không bao gồm toàn bộ RAM động của suy luận.
3. Wokwi có thể thử GPIO/state machine bằng nguồn frame hoặc kết quả giả;
   không mặc định hỗ trợ OV2640 hay mọi toán tử model. Chỉ công bố đã chạy
   model trên simulator khi đã kiểm tra thực sự.
4. Khi có board: chạy cùng model/ảnh cố định để đo latency/bộ nhớ, sau đó thay
   bằng camera thật và đánh giá nhận diện với người đã đăng ký/người lạ.

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

Mẫu đã đăng ký bằng firmware thử cũ (namespace `mfn_s8_v1`, khóa theo ID số)
không dùng cho khóa; cần đăng ký lại theo thẻ.

## Tài liệu

- https://docs.wokwi.com/guides/esp32
- https://docs.wokwi.com/getting-started/supported-hardware
- https://github.com/espressif/esp-who
