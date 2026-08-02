# Python JSON API Server

[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![CI](https://github.com/dangkhoa2016/Python-JSON-API-Server/actions/workflows/ci.yml/badge.svg)](https://github.com/dangkhoa2016/Python-JSON-API-Server/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> 🌐 Language / Ngôn ngữ: [English](README.md) | **Tiếng Việt**

REST API tương thích JSONPlaceholder được xây dựng với **FastAPI**, **SQLAlchemy** (async SQLite) và **Redis** rate limiting tùy chọn — phản ánh đầy đủ tính năng của phiên bản Node.js.

## Điểm nổi bật

- **FastAPI + async SQLAlchemy** — Stack async hiện đại với schema Pydantic type-safe và tài liệu OpenAPI tự động.
- **Rate limiting đa tầng** — Hai tầng dự phòng: Redis (Lua nguyên tử) → in-memory (LRU, 10k mục). Circuit breaker, trích xuất trusted proxy dựa trên CIDR, và thời gian chặn tăng dần.
- **Docker sẵn sàng** — Multi-stage build, **user không phải root**, tự động setup DB khi khởi động, file `.env` bị loại trừ. Dữ liệu SQLite được lưu trữ trong Docker volume.
- **Cấu hình runtime** — Cập nhật cài đặt rate-limit và Redis qua admin API **không cần khởi động lại**. Thay đổi có hiệu lực ngay lập tức qua in-memory override.
- **Bảo mật Argon2** — Mật khẩu admin được hash bằng argon2, kết quả được cache 5s TTL và 1k mục LRU. Body request CRUD giới hạn 1 MB.
- **Xóa cascade** — Xóa user sẽ xóa posts, albums, và todos. Xóa post sẽ xóa comments. Xóa album sẽ xóa photos.

## Công nghệ sử dụng

- **Python >= 3.11** — runtime
- **FastAPI** — web framework async
- **SQLAlchemy 2.0** (chế độ async) — ORM với async SQLite qua aiosqlite
- **aiosqlite** — driver SQLite async
- **Redis** (tùy chọn) — rate limiting qua Lua scripts
- **argon2-cffi** — hash mật khẩu an toàn cho xác thực admin
- **pydantic-settings** — cấu hình dựa trên environment
- **uvicorn** — ASGI server
- **pytest + httpx** — kiểm thử

## Yêu cầu

- **Python >= 3.11**
- **Redis** (tùy chọn — rate limiting dự phòng về in-memory nếu không có)

## Bắt đầu nhanh

```bash
git clone <repo-url>
cd Python-JSON-API-Server

pip install -e ".[dev]"

./scripts/run.sh db:setup     # tạo bảng + seed data (tùy chọn — server cũng tự khởi tạo DB khi khởi động)
./scripts/run.sh start        # khởi động server trên http://localhost:3000
```

> Các lệnh database cũng có thể gọi trực tiếp bằng Python (ví dụ: `python -m scripts.db_setup`). Xem [Scripts](#scripts) để biết tham chiếu đầy đủ.

## Scripts

`run.sh` cung cấp CLI thống nhất cho các lệnh database, server và kiểm thử.

```bash
./scripts/run.sh <command>
```

### Database

| Lệnh              | Mô tả                                           |
|--------------------|-------------------------------------------------|
| `db:setup`         | Chạy migrate + seed + seed-settings (setup đầy đủ) |
| `db:migrate`       | Tạo tất cả 7 bảng                               |
| `db:seed`          | Seed dữ liệu từ JSONPlaceholder                 |
| `db:seed-settings` | Seed cài đặt mặc định từ environment            |
| `db:set-admin-key` | Đặt/thay đổi `ADMIN_KEY` trong DB (ghi vào `.env` trong development) |

### Server

| Lệnh    | Mô tả                                              |
|---------|----------------------------------------------------|
| `start` | Khởi động uvicorn trên port `$PORT` (mặc định: 3000) |
| `prod`  | Khởi động chế độ production (2 workers, không reload) |
| `dev`   | Khởi động với auto-reload khi thay đổi code        |

### Kiểm thử

| Lệnh           | Mô tả                                              |
|-----------------|----------------------------------------------------|
| `test`          | Chạy tất cả tests                                  |
| `test:watch`    | Chạy tests ở chế độ watch                          |
| `test:coverage` | Chạy tests + tạo báo cáo HTML trong `htmlcov/`     |

```bash
./scripts/run.sh test              # chạy tất cả tests
./scripts/run.sh test -k "test_"   # truyền thêm tham số cho pytest
./scripts/run.sh test:coverage     # tạo báo cáo coverage HTML
```

## Docker

### Build

```bash
docker build -t python-json-api-server .
```

### Chạy

```bash
docker run -d -p 3000:3000 -v ./storage:/app/storage --name python-json-api-server python-json-api-server
```

Entrypoint container chạy theo thứ tự cố định:

1. Migrate schema.
2. Seed local application settings.
3. Seed dữ liệu demo từ xa — chỉ khi `SEED_DATA_ON_STARTUP=true`.
4. Chạy lệnh khởi động server.

| Chế độ | `SEED_DATA_ON_STARTUP` | Kết quả |
|---|---:|---|
| Production/mặc định | `false` | Migrate và seed local settings; **không bao giờ** gọi provider dữ liệu mẫu bên ngoài. |
| Demo | `true` | Migrate, seed settings, rồi seed dữ liệu mẫu idempotent trước khi server khởi động. |

Bản deploy demo bật flag này sẽ **thất bại rõ ràng** nếu seed dữ liệu mẫu bị timeout hoặc provider lỗi — nó không bao giờ khởi động như một demo rỗng "thành công". Seed tùy chọn chạy trong một tổng thời gian timeout duy nhất là `SEED_TIMEOUT_SECONDS` (mặc định `60`).

#### Demo (có dữ liệu mẫu)

```bash
docker run -d -p 3000:3000 \
  -e SEED_DATA_ON_STARTUP=true \
  -e SEED_TIMEOUT_SECONDS=60 \
  -v ./storage:/app/storage \
  --name python-json-api-server-demo python-json-api-server
```

Với các deployment tự quản lý dữ liệu, người vận hành có thể seed hoặc seed lại dữ liệu mẫu bằng `python -m scripts.db_seed` (hoặc `./scripts/run.sh db:seed`) — một lệnh bảo trì, không phải bước bắt buộc sau triển khai.

### Biến môi trường

```bash
docker run -d -p 3000:3000 \
  -e ADMIN_KEY=my-secret-key \
  -e REDIS_HOST=redis \
  -v ./storage:/app/storage \
  --name python-json-api-server python-json-api-server
```

### Lưu ý

- Container chạy với user `app` không phải root.
- File database được lưu trữ tại `/app/storage` (khai báo như `VOLUME`) — dữ liệu được **giữ lại qua các lần khởi động**. Khi seed demo được bật, seed tự động **bỏ qua** nếu dữ liệu resource đã tồn tại.
- File `.env` và `.env.*` bị **loại trừ** bởi `.dockerignore` và **không được copy** vào image.
- Entrypoint migrate schema và seed local settings, rồi seed dữ liệu demo từ xa chỉ khi `SEED_DATA_ON_STARTUP=true`.
- Container luôn lắng nghe trên port `3000` (hardcoded trong image). Biến môi trường `PORT` chỉ áp dụng khi chạy server bằng `./scripts/run.sh` bên ngoài Docker.

---

## Cấu hình

Tất cả cấu hình được tải từ biến môi trường (hỗ trợ file `.env` trong development qua pydantic-settings).

### Biến

| Biến                   | Mặc định   | Mô tả                                  |
|------------------------|-------------|----------------------------------------|
| `APP_ENV`               | `development` | Môi trường ứng dụng                    |
| `DEBUG_SQL`             | `false`       | Bật logging query SQL                  |
| `PORT`                 | `3000`      | Port server                            |
| `DB_PATH`              | `./storage/data.db` | Đường dẫn file database SQLite |
| `REDIS_URL`            | _(none)_    | URL kết nối Redis (ưu tiên cao nhất). Định dạng: `redis://user:password@host:port/db` |
| `REDIS_HOST`           | `127.0.0.1` | Host Redis                             |
| `REDIS_PORT`           | `6379`      | Port Redis                             |
| `REDIS_DB`             | `0`         | Chỉ số database Redis                  |
| `REDIS_PASSWORD`       | _(none)_    | Mật khẩu Redis (cho `AUTH`)            |
| `RATE_LIMIT_ENABLED`   | `true`      | Bật/tắt rate limiting                  |
| `RATE_LIMIT_MAX`       | `100`       | Số request tối đa mỗi cửa sổ thời gian |
| `RATE_LIMIT_WINDOW_MS` | `60000`     | Cửa sổ thời gian tính bằng mili giây (mặc định 1 phút) |
| `TRUSTED_PROXIES`      | `127.0.0.1,::1` | Danh sách IP/CIDR phân tách bằng dấu phẩy được phép đặt `X-Forwarded-For`/`X-Real-IP` (ví dụ `10.0.0.0/8`) |
| `SEED_API_BASE_URL`    | `https://jsonplaceholder.typicode.com` | URL cơ sở cho API dữ liệu seed |
| `SEED_DATA_ON_STARTUP` | `false` | Seed dữ liệu demo từ xa khi container khởi động (điều khiển bootstrap container, không phải runtime setting) |
| `SEED_TIMEOUT_SECONDS` | `60` | Tổng thời gian timeout cho seed demo tùy chọn; container thất bại nếu hết hạn |
| `MAX_BODY_SIZE`        | `1048576`   | Kích thước body request tối đa tính bằng byte |
| `DEFAULT_PAGE_SIZE`    | `10`        | Số kết quả mặc định mỗi trang cho phân trang `_page`/`_limit` |
| `MAX_PAGE_SIZE`        | `100`       | Số kết quả tối đa trả về cho mỗi request |
| `ADMIN_KEY`            | `""`        | Master key để xác thực request admin API (Bearer token) |
| **Cập nhật runtime**  | —           | PATCH `RATE_LIMIT_ENABLED`, `RATE_LIMIT_MAX`, `RATE_LIMIT_WINDOW_MS`, `DEBUG_SQL`, `DEFAULT_PAGE_SIZE`, `REDIS_URL`, `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB`, hoặc `REDIS_PASSWORD` qua admin API sẽ áp dụng thay đổi ngay lập tức — không cần khởi động lại server |

---

## API Endpoints

### Tài nguyên

| Phương thức | Đường dẫn                     | Mô tả                        |
|-------------|-------------------------------|------------------------------|
| `GET`       | `/api/users`                  | Liệt kê tất cả users         |
| `GET`       | `/api/users/:id`              | Lấy user theo ID             |
| `GET`       | `/api/users/:id/posts`        | Posts của user                |
| `GET`       | `/api/users/:id/albums`       | Albums của user               |
| `GET`       | `/api/users/:id/todos`        | Todos của user                |
| `GET`       | `/api/posts`                  | Liệt kê tất cả posts         |
| `GET`       | `/api/posts/:id`              | Lấy post theo ID             |
| `GET`       | `/api/posts/:id/comments`     | Comments trên post            |
| `GET`       | `/api/comments`               | Liệt kê tất cả comments      |
| `GET`       | `/api/albums`                 | Liệt kê tất cả albums        |
| `GET`       | `/api/albums/:id/photos`      | Photos trong album            |
| `GET`       | `/api/photos`                 | Liệt kê tất cả photos        |
| `GET`       | `/api/todos`                  | Liệt kê tất cả todos         |
| `POST`      | `/api/:table`                 | Tạo resource mới             |
| `PUT`       | `/api/:table/:id`             | Thay thế toàn bộ resource    |
| `PATCH`     | `/api/:table/:id`             | Cập nhật một phần            |
| `DELETE`    | `/api/:table/:id`             | Xóa resource                 |

> **Xóa cascade**: Xóa `user` sẽ xóa `posts`, `albums`, và `todos`. Xóa `post` sẽ xóa `comments`. Xóa `album` sẽ xóa `photos`.

> **Body contract**: Tất cả request `POST`, `PUT`, và `PATCH` phải có body là JSON object. Body không phải object (`null`, array, string, number, empty) bị từ chối với `400 Bad Request`. `POST` tạo resource mới (các trường thiếu sẽ dùng giá trị mặc định). `PUT` thực hiện thay thế toàn bộ — tất cả trường được ghi từ request body, các trường không được chỉ định sẽ được đặt về giá trị mặc định. `PATCH` thực hiện cập nhật một phần — chỉ các trường được chỉ định mới thay đổi.

> **Lưu ý**: Bảng `settings` **không** được expose qua các endpoint CRUD generic — `GET /api/settings` trả về `404`. Chỉ có thể truy cập qua admin API (`GET /api/admin/settings`, `PATCH /api/admin/settings/:key`).

> **Lưu ý**: Các endpoint ghi (`POST`, `PUT`, `PATCH`, `DELETE`) cố ý để mở — bất kỳ ai cũng có thể tạo, ghi đè, hoặc xóa resource, mô phỏng theo semantics của JSONPlaceholder. Dữ liệu không bền; có thể reset bất kỳ lúc nào qua admin reset endpoint (`POST /api/admin/reset-database`).

### Lọc query string & Phân trang

```bash
# Lọc posts theo userId
GET /api/posts?userId=1

# Lọc todos theo userId và trạng thái completed
GET /api/todos?userId=1&completed=false

# Lọc comments theo postId
GET /api/comments?postId=1
```

Các cột có thể lọc thay đổi theo bảng (ví dụ: `title`, `email`, `username`). Trường `completed` chấp nhận chuỗi `true`/`false`.

### Phân trang

| Tham số   | Mô tả                                          | Ví dụ                       |
|-----------|------------------------------------------------|------------------------------|
| `_page`   | Số trang (bắt đầu từ 1), dùng với `_limit`    | `?_page=1&_limit=10`        |
| `_limit`  | Số mục mỗi trang (mặc định: `DEFAULT_PAGE_SIZE`) | `?_page=2&_limit=5`        |
| `_start`  | Chỉ số offset để slicing                       | `?_start=10&_end=20`        |
| `_end`    | Chỉ số kết thúc (exclusive) để slicing         | `?_start=0&_end=5`          |

`_limit` bị giới hạn ở `MAX_PAGE_SIZE` (mặc định 100), và khi cung cấp cả `_start` lẫn `_end` thì cửa sổ cũng bị giới hạn. Lưu ý rằng `_start` đơn lẻ (không có `_end`) không bị giới hạn — nó trả về mọi bản ghi từ offset đó trở đi.

### Tìm kiếm

Tìm kiếm trên các cột text bằng tham số `q`. Các cột có thể tìm kiếm thay đổi theo bảng:

| Bảng       | Các cột có thể tìm kiếm                   |
|------------|-------------------------------------------|
| `users`    | `name`, `username`, `email`               |
| `posts`    | `title`, `body`                           |
| `comments` | `name`, `email`, `body`                   |
| `albums`   | `title`                                   |
| `photos`   | `title`                                   |
| `todos`    | `title`                                   |

```bash
# Tìm posts theo title hoặc body
GET /api/posts?q=first

# Kết hợp tìm kiếm với lọc
GET /api/posts?q=Post&userId=1

# Tìm todos
GET /api/todos?q=groceries
```

### Sắp xếp

| Tham số   | Giá trị         | Mô tả                                |
|-----------|----------------|--------------------------------------|
| `_sort`   | tên cột        | Cột để sắp xếp                      |
| `_order`  | `asc` / `desc` | Hướng sắp xếp (mặc định: `asc`)     |

```bash
# Sắp xếp posts theo title tăng dần
GET /api/posts?_sort=title&_order=asc

# Sắp xếp posts theo title giảm dần
GET /api/posts?_sort=title&_order=desc

# Kết hợp sắp xếp với phân trang
GET /api/posts?_sort=id&_order=desc&_limit=2
```

### System Endpoints

| Đường dẫn                         | Mô tả                                |
|-----------------------------------|--------------------------------------|
| `GET /`                           | Thông tin API với các endpoint có sẵn |
| `GET /api`                        | Thông tin API (giống trên)           |
| `GET /health`                     | Trạng thái server (DB, Redis, bảng, cài đặt rate limit) |
| `GET /api/health`                 | Giống trên                           |
| `GET /docs`                       | Tài liệu API tương tác (Swagger UI)  |
| `GET /redoc`                      | Tài liệu API ReDoc                    |
| `GET /openapi.json`               | OpenAPI schema                        |
| `GET /favicon.ico`                | Favicon (không trong OpenAPI schema) |
| `GET /favicon.png`                | Favicon PNG (không trong OpenAPI schema) |
| `GET /api/admin/settings`         | Liệt kê tất cả settings (cần xác thực) |
| `PATCH /api/admin/settings/:key`  | Cập nhật giá trị setting — thay đổi rate-limit & Redis có **hiệu lực ngay** tại runtime (cần xác thực) |
| `POST /api/admin/reset-database`  | Xóa dữ liệu bảng và seed lại từ JSONPlaceholder (cần xác thực) |

### Admin API

Các endpoint admin được bảo vệ bởi xác thực Bearer token bằng biến môi trường `ADMIN_KEY`. Giá trị settings được lưu trong bảng `settings` của database.

```bash
# Liệt kê tất cả settings
curl http://localhost:3000/api/admin/settings \
  -H "Authorization: Bearer my-secret-key"

# Cập nhật một setting
curl -X PATCH http://localhost:3000/api/admin/settings/ADMIN_KEY \
  -H "Authorization: Bearer my-secret-key" \
  -H "Content-Type: application/json" \
  -d '{"value": "new-secret-key"}'

# Đặt lại database (xóa tất cả dữ liệu và lấy lại từ JSONPlaceholder)
curl -X POST http://localhost:3000/api/admin/reset-database \
  -H "Authorization: Bearer my-secret-key" \
  -H "Content-Type: application/json" \
  -d '{"confirm": true}'
```

`ADMIN_KEY` được hash bằng **argon2** trước khi lưu. Khi cập nhật mật khẩu qua `PATCH /api/admin/settings/ADMIN_KEY`, giá trị mới tự động được hash. Mật khẩu không bao giờ được lưu dạng plaintext.

**Khởi tạo / thay đổi `ADMIN_KEY`:** Xác thực admin có hai nguồn sự thật — biến môi trường `ADMIN_KEY` (hoặc file `.env` trong development) đóng vai trò công tắc tổng (admin API bị tắt khi biến này rỗng), và bảng **`settings`** lưu credential đã hash argon2 mà các Bearer token được xác minh dựa trên. Ở lần khởi động đầu tiên với database mới, quá trình seed settings sao chép giá trị từ environment (đã hash) vào bảng đó.

Do đó, server khởi động với `ADMIN_KEY` rỗng sẽ bị khóa khỏi admin API — kể cả sau khi seed, vì seed chỉ ghi lại những gì environment cung cấp. Để đặt hoặc thay đổi key mà không cần xóa database:

```bash
./scripts/run.sh db:set-admin-key my-new-secret-key
```

Bỏ qua tham số để nhập secret tương tác mà không hiển thị trên màn hình:
```bash
./scripts/run.sh db:set-admin-key
ADMIN_KEY: (gõ, không echo)
```

Lệnh này hash giá trị và upsert vào bảng `settings`. Trong development, lệnh cũng ghi `ADMIN_KEY` vào `.env` để cổng xác thực hoạt động ở lần khởi động sau — hãy khởi động lại server sau khi chạy. Key phải khác rỗng và không chứa khoảng trắng; lệnh in cảnh báo nếu key ngắn hơn 12 ký tự. Trong môi trường không phải development, CLI chỉ cập nhật database — hãy tự đặt biến môi trường `ADMIN_KEY`.

**Cập nhật cấu hình runtime**: Khi PATCH cài đặt rate-limit (`RATE_LIMIT_ENABLED`, `RATE_LIMIT_MAX`, `RATE_LIMIT_WINDOW_MS`), cài đặt logging hoặc phân trang (`DEBUG_SQL`, `DEFAULT_PAGE_SIZE`), hoặc cài đặt kết nối Redis (`REDIS_HOST`, `REDIS_PORT`, `REDIS_DB`, `REDIS_PASSWORD`, `REDIS_URL`), server áp dụng thay đổi ngay lập tức — không cần khởi động lại.

Kết quả xác thực argon2 được **cache trong memory 5 giây** mỗi token, tránh việc hash lặp lại trong các request admin liên tiếp. Khi có lỗi, kết quả cũng được cache là invalid — ngăn chặn side-channel leak qua timing hoặc error message.

---

## Response Headers

Response bao gồm header CORS và rate-limit:

```
Access-Control-Allow-Origin: *                 ← chỉ có khi request mang header Origin (trình duyệt/CORS)
X-RateLimit-Limit:     100                     ← theo phương thức: 100 (GET/HEAD), 50 (POST/PUT/PATCH), 33 (DELETE)
X-RateLimit-Remaining: 99
X-RateLimit-Reset:     <giây epoch>            ← Unix timestamp tuyệt đối của thời điểm hết cửa sổ/chặn
X-RateLimit-Store:     redis                   ← "redis" hoặc "memory"
```

Header `X-RateLimit-*` chỉ được gửi khi rate limiting được bật, request đi vào route bị giới hạn (không phải `/health`, `/api/health`, hay `/favicon.ico`), và xác định được IP client.

Khi vượt quá rate limit, response `429 Too Many Requests` được trả về kèm header `Retry-After`:

```
X-RateLimit-Limit:     100
X-RateLimit-Remaining: 0
X-RateLimit-Reset:     <giây epoch>            ← Unix timestamp tuyệt đối khi hết thời gian chặn
X-RateLimit-Store:     redis
Retry-After:           300
```

```json
{
  "error": "Too Many Requests",
  "message": "Rate limit exceeded. Max 100 requests per 60s window.",
  "retryAfter": 300
}
```

> **Lưu ý đa worker:** store rate-limit trong bộ nhớ là riêng cho từng tiến trình. Khi chạy nhiều uvicorn worker (`./scripts/run.sh prod`, dùng 2 worker), số đếm không được chia sẻ giữa các worker. Để có giới hạn toàn cục nhất quán, hãy trỏ `REDIS_URL` (hoặc `REDIS_HOST`/`REDIS_PORT`) tới một instance Redis dùng chung.

---

## Ví dụ

```bash
# Liệt kê users
curl http://localhost:3000/api/users

# Tạo post mới
curl -X POST http://localhost:3000/api/posts \
  -H "Content-Type: application/json" \
  -d '{"userId": 1, "title": "Hello", "body": "World"}'

# Cập nhật một phần
curl -X PATCH http://localhost:3000/api/posts/1 \
  -H "Content-Type: application/json" \
  -d '{"title": "Updated title"}'

# Xóa
curl -X DELETE http://localhost:3000/api/posts/1

# Health check
curl http://localhost:3000/health
```

## Database

- **7 bảng:** `users`, `posts`, `comments`, `albums`, `photos`, `todos`, `settings`
- **Chế độ WAL** cho hiệu suất đọc đồng thời tốt hơn
- **Foreign keys** được enforced qua `PRAGMA foreign_keys=ON`
- **Dữ liệu seed** được lấy từ [JSONPlaceholder](https://jsonplaceholder.typicode.com) trong lần chạy đầu tiên:
  - 10 users (`address` và `company` được lưu dạng JSON, parse khi đọc)
  - 100 posts
  - 500 comments
  - 100 albums
  - 5000 photos
  - 200 todos
  - 14 settings (biến môi trường)

### Database Scripts

| Script        | Lệnh                           | Mô tả                                             |
|---------------|--------------------------------|---------------------------------------------------|
| `db:setup`    | `./scripts/run.sh db:setup`            | Chạy migrate + seed + seed-settings               |
| `db:migrate`  | `./scripts/run.sh db:migrate`          | Tạo tất cả 7 bảng                                 |
| `db:seed`     | `./scripts/run.sh db:seed`             | Seed dữ liệu từ JSONPlaceholder                   |

---

## Kiểm thử

Sử dụng **pytest** với **pytest-asyncio** để hỗ trợ async testing và **httpx** cho HTTP client testing.

```bash
./scripts/run.sh test              # Chạy tất cả tests (hiện coverage qua pyproject.toml addopts)
./scripts/run.sh test -v           # Output chi tiết
./scripts/run.sh test -k "test_"   # Chạy tests cụ thể
./scripts/run.sh test:coverage     # Tạo báo cáo HTML coverage trong htmlcov/
```

## Dự án tương tự

- [Nodejs-JSON-API-Server](https://github.com/dangkhoa2016/Nodejs-JSON-API-Server) — Phiên bản Node.js gốc chỉ dùng các module tích hợp sẵn, với cùng bộ tính năng.
- [JSON-API-Server-With-Dashboard-UI](https://github.com/dangkhoa2016/JSON-API-Server-With-Dashboard-UI) — Phiên bản mở rộng với dashboard UI tích hợp sẵn để quản lý dữ liệu và giám sát API.

## Cài đặt Runtime

14 cài đặt được lưu trong bảng `settings` và tải lúc khởi động:

| Key | Mặc định | Kiểu | Mô tả |
|---|---|---|---|
| `APP_ENV` | `development` | string | Môi trường ứng dụng |
| `PORT` | `3000` | int | Port server HTTP |
| `DB_PATH` | `./storage/data.db` | string | Đường dẫn database SQLite |
| `DEBUG_SQL` | `false` | bool | Bật logging query SQL |
| `REDIS_HOST` | `127.0.0.1` | string | Hostname Redis server |
| `REDIS_PORT` | `6379` | int | Port Redis server |
| `REDIS_DB` | `0` | int | Chỉ số database Redis |
| `REDIS_URL` | _(trống)_ | string | URL Redis đầy đủ (ghi đè host/port/db) |
| `REDIS_PASSWORD` | _(trống)_ | string | Mật khẩu Redis |
| `RATE_LIMIT_ENABLED` | `true` | bool | Bật rate limiting |
| `RATE_LIMIT_MAX` | `100` | int | Số request tối đa mỗi cửa sổ |
| `RATE_LIMIT_WINDOW_MS` | `60000` | int | Thời lượng cửa sổ tính bằng ms |
| `DEFAULT_PAGE_SIZE` | `10` | int | Số kết quả mỗi trang phân trang |
| `ADMIN_KEY` | _(trống)_ | string | Admin auth key (hash argon2) |

Cài đặt được seed từ đối tượng pydantic `Settings` ở lần khởi động đầu tiên với database mới, nên biến môi trường và file `.env` được ưu tiên hơn các giá trị mặc định đã gõ ở trên. Ở các lần khởi động sau, việc seed bị bỏ qua nếu bảng `settings` đã có dữ liệu. Admin API có thể cập nhật chúng tại runtime mà không cần khởi động lại. Có thể đặt hoặc thay đổi `ADMIN_KEY` ngoài API qua `./scripts/run.sh db:set-admin-key` (với secret là tham số, hoặc nhập tương tác không echo) — trong development lệnh này cũng cập nhật `.env`.

## Docker

```bash
# Build và chạy với volume SQLite mới
./scripts/container_smoke.sh python-json-api-server:smoke
```

Script smoke tạo volume Docker mới mỗi lần chạy, khởi động container, kiểm tra `/health` (30 giây timeout), và dọn dẹp khi thoát.

## Giấy phép

[MIT](LICENSE)
