# API contract v1.0

## Quy ước chung

- JSON có `schemaVersion: "1.0"`.
- JPEG raw tối đa 1 MiB, `Content-Type: image/jpeg`.
- Timeout mặc định 10 giây.
- Không endpoint nào trả embedding hoặc điều khiển khóa.
- `X-Frame-Id` tùy chọn được giữ nguyên trong response `/predict`.
- `/enroll`, `/persons` và `/persons/{personId}` yêu cầu `X-Admin-Key` trùng biến môi trường `SMARTLOCK_ADMIN_API_KEY`. Đây là khóa prototype; production cần TLS, secret manager, rotation, authorization/audit và rate limiting.

## Endpoint

| Method | Path | Input | Kết quả chính |
|---|---|---|---|
| GET | `/health` | — | `ready` hoặc `not_ready` |
| POST | `/predict` | raw JPEG | `PredictionResponse` |
| POST | `/enroll` | raw JPEG, `X-Person-Id`, admin key | số mẫu của người dùng |
| GET | `/persons` | admin key | personId và sampleCount; không có embedding |
| DELETE | `/persons/{personId}` | admin key | 204 hoặc 404 |

`PredictionResponse` chứa `schemaVersion`, `frameId`, `status`, `personId`, `similarity`, `model{name,version}`, `processingMs`. `similarity` là cosine score, không phải xác suất.

## HTTP/error

- 200: request hợp lệ; trạng thái nhận diện nằm trong body.
- 204: xóa thành công.
- 400: `INVALID_CONTENT_LENGTH`.
- 401: `UNAUTHORIZED`.
- 404: `PERSON_NOT_FOUND`.
- 409: `ENROLLMENT_REJECTED`.
- 413: `PAYLOAD_TOO_LARGE`.
- 415: `UNSUPPORTED_MEDIA_TYPE`.
- 422: validation hoặc ảnh không đủ điều kiện enroll.
- 503: `NOT_READY` khi model/detector/database không khởi tạo được.
- 504: `PROCESSING_TIMEOUT`.

Error JSON thống nhất: `{"schemaVersion":"1.0","error":{"code":"...","message":"..."}}`.
