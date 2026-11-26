# ESP32-S3 fixed JPEG probe

Chương trình ESP-IDF độc lập, dùng model thật trên ESP32-S3 và JPEG cố định
thay camera. Build trên PC chỉ kiểm tra compile/link và dung lượng; không có
nghĩa model đã chạy. Không có driver camera, servo, RFID, MQTT hay lệnh mở khóa.

Đã bổ sung [chạy QEMU và kết quả thực thi](QEMU.md): model đã chạy, nhưng kiểm
tra danh tính chưa đạt. Bản strict vẫn từ chối nhiều detection; chế độ fixture
compat chỉ kiểm tra ảnh cố định theo hành vi ví dụ upstream.

## Baseline build đầu tiên — 2026-11-26

- Cross-compile/link và kiểm tra partition: **PASS**, target ESP32-S3.
- Application binary: **2,880,672 byte** (khoảng 2.75 MiB), vừa app partition
  12 MiB của probe. Đây chưa phải kích thước firmware SmartLock tích hợp.
- Model đóng gói: detector **191,296 byte**, MFN **1,295,280 byte**.
- Linker: DIRAM **85,399 byte** (code 64,303 + data 13,064 + bss 8,032);
  vùng IRAM riêng **16,384 byte**. Không diễn giải phần còn trống trong bảng
  linker thành heap thực tế còn cho AI. Vùng IRAM riêng hiện dùng hết không
  có nghĩa toàn bộ RAM của chip đã hết.
- SHA-256 binary: `b7ed94eac90e451bbafe52d962ffabf41a99226d957a598ea1eda1c45c31e8e6`.
- Hash của 4 JPEG hợp lệ; kiểm tra âm tính với JPEG bị đổi nội dung đã bị từ chối.
- Bộ thử logic vector nhân tạo vẫn qua **13/13** kịch bản.
- Tại bước baseline này chưa chạy image. Kết quả QEMU tiếp theo ở QEMU.md;
  chưa có benchmark phần cứng hay độ chính xác trên tập đánh giá. Binary mới
  có thêm log và cờ mode nên kích thước/hash mới ở `../../output/probe-build.json`.

Toolchain, component cache và build nằm trong các thư mục gitignore. Binary,
ELF, map và báo cáo được tạo lại bằng lệnh build; không ghi các artifact này
vào source. Có thể thay đổi SHA binary khi đường dẫn/build metadata thay đổi.

## Bộ phiên bản

- ESP-IDF **v5.5.2**, commit `30aaf64524299d3bde422ca9a2848090d1bc5d0f`.
- `espressif/esp-dl` **3.3.14**.
- `espressif/human_face_detect` **0.5.2**, MSRMNP_S8_V1.
- `espressif/human_face_recognition` **0.3.3**, MFN_S8_V1 (int8).
- JPEG từ commit ESP-DL `24ac077101e77f14f66561b0306158ce42486e1b`;
  URL, kích thước và SHA-256 ở `main/fixtures/manifest.json`.
- Các dependency bắc cầu và hash do Component Manager ghi trong `dependencies.lock`.

Flash 16 MB, QIO và OPI PSRAM lấy theo cấu hình SmartLock. CPU 240 MHz,
PSRAM 80 MHz, cache và stack là cấu hình thử được chọn, không phải phần cứng
đã được xác nhận. Không tự giả định dung lượng PSRAM. ESP-DL hiện cần IDF từ
5.3; Arduino hiện có của SmartLock dùng nền 4.4.7 theo metadata build cũ nên
chưa ghép hai build lại.

## Chuẩn bị công cụ (Windows / PowerShell)

Từ SmartLock-EdgeAI root, cần Git và Python 3.11. Cài trong workspace:

```powershell
git clone --branch v5.5.2 --depth 1 --shallow-submodules --recursive https://github.com/espressif/esp-idf.git face-edge/.tools/esp-idf
$env:IDF_TOOLS_PATH = Join-Path $PWD 'face-edge/.tools/idf-tools'
python face-edge/.tools/esp-idf/tools/idf_tools.py --non-interactive install --targets esp32s3
python face-edge/.tools/esp-idf/tools/idf_tools.py --non-interactive install-python-env
python face-edge/tools/probe.py prepare
python face-edge/tools/probe.py build
```

Nếu `python` là 3.14, dùng đường dẫn Python 3.11 cho hai lệnh cài công cụ.
Script wrapper tự tìm Python ESP-IDF đã tạo và chỉ chấp nhận IDF v5.5.2.
Có thể đặt `IDF_PATH`, `IDF_TOOLS_PATH` để dùng bộ công cụ đã cài riêng.
Không dùng `set-target` vào project đã build cho target khác; probe chỉ dành
cho ESP32-S3.

Nếu gặp lỗi đường dẫn dài khi giải nén toolchain trên Windows, dùng ổ ảo còn
trống (ví dụ R; kiểm tra không đang dùng trước khi ánh xạ):

```powershell
subst R: "$PWD/face-edge"
$env:IDF_PATH = 'R:\.tools\esp-idf'
$env:IDF_TOOLS_PATH = 'R:\.tools\idf-tools'
$env:FACE_EDGE_PROBE_PATH = 'R:\examples\esp32s3_probe'
python R:/.tools/esp-idf/tools/idf_tools.py --non-interactive install --targets esp32s3
python face-edge/tools/probe.py build
# Sau khi mọi tác vụ build đã kết thúc:
subst R: /D
Remove-Item Env:IDF_PATH,Env:IDF_TOOLS_PATH,Env:FACE_EDGE_PROBE_PATH
```

Nếu export báo thiếu công cụ cụ thể, cài tên đó bằng `idf_tools.py install
<tool-name>`. Python cho lệnh cài nên dùng cùng bản 3.11 đã tạo môi trường IDF.

## Artifact

- `build/face_edge_probe.bin`: application image, không phải merged flash image.
- `build/face_edge_probe.elf`, `build/face_edge_probe.map`: symbols/static layout.
- `build/bootloader/bootloader.bin`, `build/partition_table/partition-table.bin`.
- `build/flasher_args.json`: offset flash đúng của build này.
- `../../output/probe-build.json`: kích thước app, chưa có số đo runtime.

Partition app 12 MiB và partition SPIFFS 1 MiB là layout dành riêng probe trong
flash 16 MiB; không chứng minh app đã vừa partition firmware sản phẩm hiện có.
RAM tĩnh trong size report không bao gồm heap, framebuffer, tensor và database
cấp phát lúc chạy. Không chuyển kích thước firmware thành lượng RAM cần dùng.

## Khi có board

Dùng môi trường ESP-IDF đã export, vào thư mục probe và chạy
`idf.py -p <PORT> flash monitor`. Flash probe sẽ thay firmware trên board.
Chỉ flash sau khi xác nhận board thực có flash/OPI PSRAM phù hợp.

Mỗi boot probe reset database trong partition `face_probe_fs`; nếu filesystem
chưa mount được sẽ format **partition probe** đó. Không dùng partition này cho
dữ liệu đăng ký thật. Probe tuần tự:

1. Giải mã ảnh người A và đăng ký một mẫu.
2. Truy vấn ảnh người B trước khi đăng ký B.
3. Đăng ký B, truy vấn ảnh khác của A và B.
4. In template ID/điểm tương đồng, thời gian decode/detect/feature+database.
5. In heap nội/PSRAM còn trống tại các mốc và giải phóng model/ảnh.

Tên người trong ảnh chỉ là fixture upstream; template ID không phải person_id
sản phẩm. Dùng ngưỡng nội bộ upstream, chưa hiệu chỉnh để mở khóa. Kết quả
được ghi như quan sát, không tự gán pass accuracy; probe không đo liveness hay
FAR/FRR. Giá trị heap nhỏ nhất là từ boot, không phải bộ nhớ đỉnh riêng của AI.
Muốn đánh giá chất lượng phải có tập người đã đăng ký/người lạ riêng biệt.

Bộ thử vector Python dùng ngưỡng minh họa và kiểm tra khoảng cách giữa hai
ứng viên. Probe này dùng đối sánh mặc định của thư viện; hai bộ thử chưa có
chính sách tương đương và không được suy từ kết quả bộ này sang bộ kia.

## Nguồn

- https://github.com/espressif/esp-dl/tree/24ac077101e77f14f66561b0306158ce42486e1b/examples/human_face_recognition
- https://components.espressif.com/components/espressif/human_face_recognition/versions/0.3.3
- https://github.com/espressif/esp-idf/tree/v5.5.2
