# SmartLock face-edge với camera thật

Bản firmware ESP-IDF 5.5.2 dùng chân camera từ SmartLock, JPEG 320×240,
detector MSRMNP và MFN int8. Driver tự nhận cảm biến. Mạch thử COM5 ghi
log OV3660 khi khởi tạo, dù cấu hình dự án trước đây mô tả OV2640.
Chạy nhận diện trên ESP32-S3.
Đây là bản thử qua UART, chưa kết nối luồng RFID, OTP hoặc servo.

Trong môi trường ESP-IDF đã thiết lập, vào thư mục này và chạy
`idf.py build`, sau đó `idf.py -p COM5 flash`. UART báo thông tin boot
và camera ở 115200 baud rồi chuyển sang 460800 baud trước dòng `READY`.
Đóng monitor trước khi chạy công cụ PC. Nếu đang dùng firmware cũ,
thêm `--baud 115200` vào lệnh Python.
Nạp bản thử thay ứng dụng đang có trên mạch. Kho mẫu dùng partition NVS
`face_live`, namespace `mfn_s8_v1`.

Từ thư mục SmartLock, chạy với Python có PySerial:

```powershell
python face-edge/tools/live_camera.py capture
python face-edge/tools/live_camera.py enroll --id 1
python face-edge/tools/live_camera.py list
python face-edge/tools/live_camera.py identify
python face-edge/tools/live_camera.py delete --id 1
```

`capture` lưu ảnh vào `face-edge/output/live/latest.jpg`. Chỉ định
`--output` để giữ ảnh riêng. `enroll` chụp ảnh mới và lưu embedding trên
mạch, giữ qua reset. Đăng ký lại cùng ID sẽ thay mẫu cũ. ID hợp lệ từ 1 đến
32. Cổng mặc định COM5, có thể đổi bằng `--port`.

Đăng ký và nhận diện yêu cầu detector trả đúng một khuôn mặt và đủ năm
điểm mốc. Nhận diện trả `MATCH` khi ứng viên tốt nhất duy nhất vượt 0,5,
hoặc `UNKNOWN`. Ngưỡng dựa trên probe hiện có, chưa hiệu chỉnh trên ảnh
camera thật. Thử riêng người đã đăng ký và người lạ trước khi dùng kết quả
cho quyết định truy cập.

## Xem trước và đăng ký trên web

Từ thư mục gốc SmartLock, đóng Serial Monitor và chạy:

```powershell
python edge-ai/face-edge/tools/live_camera_web.py --port COM5
```

Mở [Camera SmartLock](http://127.0.0.1:8092). Trang cập nhật ảnh JPEG liên tục
qua USB. Nhập ID và bấm **Chụp và đăng ký** khi thấy mặt trong khung.
ESP32 lấy một frame mới cho lệnh đăng ký và gửi lại đúng JPEG đã dùng để
suy luận, kể cả khi từ chối. Web hiển thị ảnh này dưới kết quả và lưu tại
`output/live/enrollment.jpg`. Ảnh preview gần nhất nằm trong `output/live/latest.jpg`
tính từ thư mục `face-edge` chứa firmware. Embedding nằm trong NVS trên mạch.
Máy chủ web chỉ lắng nghe ở địa chỉ loopback. Dừng bằng Ctrl+C khi chạy
từ terminal.

Driver camera được ghim theo [ESP Component Registry](https://components.espressif.com/components/espressif/esp32-camera/versions/2.1.4/readme).
