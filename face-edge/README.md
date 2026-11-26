# Face edge — thử nghiệm khi chưa có mạch

Thư mục chuẩn bị tách thành repository/submodule riêng. Hiện là thư mục bình
thường trong SmartLock; chưa phải Git submodule. Có bản thử ESP-IDF/model thật
độc lập trong `examples/esp32s3_probe`; chưa tích hợp vào firmware khóa.

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

## Thiết kế tích hợp dự kiến

Firmware sở hữu camera/framebuffer. Module nhận view ảnh có format, kích
thước, frame ID và thời hạn sống; xử lý xong mới trả framebuffer. Module trả
person_id/status/similarity/model_version, không gọi servo. LockController
quyết định quyền truy cập. Chế độ mock phải tách build và không được phép mở
khóa vật lý. Kho embedding phải lưu model/schema version; đổi model cần kiểm
tra tương thích hoặc đăng ký lại. Đăng ký/xóa phải có phiên quản trị hợp lệ.

Chưa đổi firmware vì cần giải quyết GPIO 0 dùng chung keypad/servo, kiểm chứng
cách ghép hệ build IDF/Arduino và làm mới impact graph trước khi tích hợp. Không tự chọn GPIO
thay thế khi chưa xác nhận sơ đồ phần cứng mục tiêu.

## Chuyển thành submodule thật

Khi có repository riêng: đưa nội dung này sang repository đó và commit/push;
sau đó thay thư mục hiện tại bằng gitlink tại cùng đường dẫn, ghim commit.
Không chạy `git init` lồng trong thư mục rồi coi đó là submodule. Repository
chính phải ghi `.gitmodules` và gitlink, tương tự `admin-module` hiện có.

## Tài liệu

- https://docs.wokwi.com/guides/esp32
- https://docs.wokwi.com/getting-started/supported-hardware
- https://github.com/espressif/esp-who
