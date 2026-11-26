# Chạy suy luận ESP32-S3 bằng QEMU

## Kết quả thực thi — 2026-11-26

**Đã chạy binary ESP32-S3 và model thật, chưa đạt kiểm tra nhận diện.**
Python chỉ chuẩn bị flash/khởi động emulator/đọc UART, không thay model.

| Kiểm tra | Kết quả |
| --- | --- |
| Boot, flash 16 MiB | Đạt |
| OPI PSRAM | Nhận 8 MiB giả lập; chưa xác nhận board thật |
| Giải mã JPEG | Ảnh A 300×300; pixel mẫu gần decoder trên PC |
| Detector strict | Không đạt: 7 detection cho ảnh A chỉ có một người; từ chối đăng ký |
| Fixture compatibility | Chạy hết 5 lượt decode/detect/feature+database |
| Đăng ký A rồi B | Đạt, 2 mẫu |
| B trước khi đăng ký | Từ chối đúng, không khớp A |
| Ảnh khác của A | Khớp ID 1, similarity khoảng 0.529 |
| Ảnh khác của B sau đăng ký | Không khớp; mong đợi ID 2 nên kiểm tra thất bại |
| Tổng thể | `recognition_checks_failed`, runner trả exit code 1 |

Chưa xác định sai lệch do model/postprocessor, preprocessing hay emulator.
Không sửa dependency hay hạ ngưỡng để làm kiểm tra đạt. Không suy ra độ chính
xác, tốc độ hoặc RAM trên board thật từ lần chạy này.

## Chạy ngay khi đã có artifact build

Từ SmartLock-EdgeAI root:

```powershell
python face-edge/tools/setup_qemu.py
python face-edge/tools/run_qemu.py
```

Setup tải archive chính thức đã ghim, kiểm tra SHA-256 trước khi giải nén;
dùng lại archive nếu đã có. Windows cần Git for Windows có DLL
`mingw64/bin/libiconv-2.dll`; script thêm DLL path vào môi trường tiến trình,
không thay PATH hệ thống.

Runner đọc `build/flasher_args.json` để ghép bootloader/partition/app, đệm 0xff
đến kích thước flash và kiểm tra segment không chồng lấn/vượt biên. Mỗi lần
chạy tạo lại flash thử; không giữ database cũ. Không thao tác cổng COM hay mạch
vật lý. Không bật NIC hoặc GUI. `--psram-mb 4` đổi RAM giả lập; `--timeout 120`
là giới hạn thời gian host, không phải latency ESP32.

## Hai chế độ probe

### Đối chứng điểm mốc trên cặp ảnh B

Bản fixture compat ghi thêm bốn dòng `B_CONTROL`. Cùng JPEG, decoder, MFN
và phép tích vô hướng của ESP-DL. Chỉ thay nguồn năm điểm mốc trên mỗi ảnh.
Các điểm thủ công được đánh dấu gần đúng trên hai JPEG 300×300 đã ghim.

| Điểm mốc đăng ký | Điểm mốc truy vấn | Điểm thô |
| --- | --- | ---: |
| Detector | Detector | 0,065714 |
| Thủ công | Detector | 0,263459 |
| Detector | Thủ công | 0,287944 |
| Thủ công | Thủ công | 0,730340 |

Với ngưỡng hiện tại 0,5, chỉ tổ hợp thủ công ở cả hai phía vượt ngưỡng.
Điều này xác định chất lượng điểm mốc và căn chỉnh là yếu tố ảnh hưởng
trực tiếp trên cặp B. Chưa xác định được nguyên nhân detector sinh điểm
mốc kém, cũng chưa có số liệu trên tập người lạ để đổi ngưỡng.
Giữ MFN làm mốc so sánh và kiểm tra detector có năm điểm mốc trên nhiều
fixture, gồm ảnh không mặt và nhiều mặt. Dùng cùng bộ ảnh trên board thật
để đối chiếu số vùng và tọa độ điểm mốc với QEMU trước khi chọn detector.
Điểm mốc thủ công chỉ dùng cho đối chứng, không đưa vào luồng mở khóa.

Probe cũng in `DETECTOR_AUDIT` cho ba cảnh cố định: nền xám 300×300,
ảnh A 300×300 và ảnh A/B ghép cạnh nhau 600×300. Mỗi detection có một
dòng `LANDMARKS` chứa điểm, khung và năm cặp tọa độ. Dùng cùng bộ binary
đã build với `--fixture-compat` trên QEMU và board để thu thêm `B_CONTROL`.
Lưu UART của board rồi lọc cả hai log bằng
`rg 'DETECTOR_AUDIT|LANDMARKS|B_CONTROL' <log>`. So số vùng trước, sau đó
ghép theo vị trí khung để so tọa độ và so bốn điểm B–B. Cảnh ghép kiểm
tra số mặt với input 600×300, khác kích thước frame camera hiện tại.

Thiết lập môi trường ESP-IDF/đường dẫn ngắn theo README trước khi build:

```powershell
# Mặc định: phải có đúng một detection.
python face-edge/tools/probe.py build
python face-edge/tools/run_qemu.py --output-dir face-edge/output/qemu-strict

# Chỉ dùng cho 4 JPEG cố định đã xác minh hash.
python face-edge/tools/probe.py build --fixture-compat
python face-edge/tools/run_qemu.py --output-dir face-edge/output/qemu-fixture-compat
```

Fixture compat cho HumanFaceRecognizer chọn detection lớn nhất như ví dụ
upstream; không đổi model hay ngưỡng. Chế độ này không chứng minh detector
đúng, không dùng làm chính sách mở khóa. Cờ CMake mặc định OFF; cần yêu cầu
`--fixture-compat` khi build. Chế độ có trong log MODE và báo cáo build.
Binary được kiểm tra cuối trong workspace hiện là fixture compat.

## Báo cáo và cách đọc

Trong `face-edge/output/qemu/`:

- `qemu-uart.log`: log đến cleanup/panic/timeout.
- `qemu-result.json`: lệnh/phiên bản emulator, hash segment, kết quả từng check,
  danh tính, timing và snapshot bộ nhớ giả lập.
- `qemu-flash.bin`: image dùng một lần, có thể bị QEMU ghi filesystem. Hash
  trong JSON là hash trước khi chạy.

`model_execution_completed` khác `functional_pass`. Dòng firmware
`PROBE completed=true` chỉ xác nhận đã chạy hết, không xác nhận nhận diện đúng.
Runner còn kiểm tra hai lần đăng ký, B trước đăng ký bị từ chối, A khớp ID 1,
B khớp ID 2, đủ timing và không panic. `strict_detector_pass` vẫn false nếu đã
dùng lựa chọn nhiều detection trong fixture compat.

Trạng thái `functional_pass` dành cho strict; `fixture_compat_pass` chỉ cho
fixture; `recognition_checks_failed` nghĩa model chạy hết nhưng danh tính
không đạt; `detector_rejected_fixture` nghĩa dừng vì số mặt; các trạng thái
panic/PSRAM/timeout là lỗi thực thi. Runner dừng QEMU khi có cleanup nên mã
thoát tiến trình QEMU có thể là 1; không dùng riêng mã đó để kết luận AI.
Timing chứa overhead log và không là benchmark phần cứng. Memory là snapshot,
không phải peak tensor memory.

## Công cụ được ghim và kiểm tra host

QEMU `esp-develop-9.2.2-20261109`, Windows x64. Manifest trong
`tools/qemu-tool.json`; archive SHA-256:
`1ffa852b5f80ac6d51cdfac463658323c27a22b94c0d7e74b58065b00b2bf25f`.
Bản `20250817` đi kèm IDF đã thử và dừng ở SPIFFS trước model; bản mới qua được
điểm dừng đó. Có thể dùng `--qemu <executable>` để tái hiện so sánh.

```powershell
python -m unittest discover -s face-edge/tools -p test_qemu_runner.py -v
```

6 kiểm tra parser/merge đã qua: không coi boot-only, đảo ID, panic, thiếu
cleanup hoặc compat là strict pass; kiểm tra offset/padding/chồng lấn. Đây là
test công cụ, không thay kết quả model. Bộ thử vector Python cũ vẫn tách riêng.

## Nguồn chính thức

- https://github.com/espressif/esp-toolchain-docs/blob/main/qemu/esp32s3/README.md
- https://github.com/espressif/qemu/releases/tag/esp-develop-9.2.2-20261109
- https://github.com/espressif/esp-dl/tree/24ac077101e77f14f66561b0306158ce42486e1b/examples/human_face_recognition
