# face_auth

Component ESP-IDF dùng chung cho firmware SmartLock và firmware thử `examples/esp32s3_live`.

```text
JPEG (camera do firmware gọi sở hữu) -> giải mã RGB888 -> MSRMNP (bbox + 5 điểm mốc)
-> MFN int8 -> embedding float -> cosine với mẫu lưu trong NVS
```

- `begin(partition, namespace)`: nạp model, mở NVS. Namespace gắn với model/schema
  (`mfn_s8_uid1` cho khóa, `mfn_s8_id1` cho công cụ thử); đổi model phải dùng namespace mới
  và đăng ký lại.
- `enroll(jpeg, len, subject, sample)`: lưu mẫu thứ `sample` (tối đa 5) cho `subject`.
- `verify(jpeg, len, subject, threshold)`: so 1:1 với mọi mẫu của `subject`, lấy điểm cao nhất.
- `identify(...)`: so 1:N trên danh sách subject (dùng cho công cụ thử).
- Trạng thái trả về: `MATCH`, `NO_MATCH`, `NO_FACE`, `MULTIPLE_FACES`, `NOT_ENROLLED`,
  `DECODE_ERROR`, `ERROR`. Nhiều mặt luôn bị từ chối.

Khóa NVS: `<48 bit FNV-1a của subject>s<sample>`, vì NVS giới hạn khóa 15 ký tự còn UID thẻ có
thể dài hơn. Component không điều khiển GPIO hay khóa; quyết định mở do `LockController`.

Giới hạn đã biết: ngưỡng 0,5 chưa hiệu chỉnh (chưa đo FAR/FRR), chưa có chống giả mạo (ảnh in,
màn hình điện thoại), detector từng bỏ sót ảnh nhiều mặt nhỏ.
