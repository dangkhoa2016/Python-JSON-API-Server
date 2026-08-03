# Hướng dẫn Deploy lên Modal.com

> 🌐 Language / Ngôn ngữ: [English](DEPLOYMENT-ON-MODAL.COM.md) | **Tiếng Việt**

## Tổng quan

Tài liệu này hướng dẫn triển khai **Python JSON API Server** lên [Modal.com](https://modal.com) dưới dạng một **Web Function** (endpoint HTTPS).

Kiến trúc triển khai:

- Bọc đối tượng `FastAPI` sẵn có (`app.main:app`) bằng `@modal.asgi_app()` thay vì chạy Uvicorn như server truyền thống. Modal hỗ trợ đầy đủ ASGI và **ASGI lifespan** — nên việc tạo bảng, nạp cấu hình, seed dữ liệu vẫn chạy bình thường.
- Vì dự án dùng **SQLite**, toàn bộ service bị giới hạn ở **một container duy nhất** (`max_containers=1`). Dữ liệu được giữ trong **Modal Volume** để sống sót qua các lần restart/cold start.
- **Redis là tùy chọn.** Khi không có Redis, ứng dụng tự chuyển sang rate limiter trong memory.

## Yêu cầu

- Tài khoản [Modal.com](https://modal.com) (đăng ký miễn phí).
- Python `>= 3.11`.
- Repository đã có file `modal_app.py` ở thư mục gốc (branch `feat/modal-deploy`).

## 1. Cài đặt Modal CLI

```bash
python -m pip install --upgrade modal
modal setup
```

Lệnh `modal setup` mở trình duyệt để đăng nhập và lưu token vào máy.

## 2. Cấu trúc file `modal_app.py`

File nằm ở thư mục gốc, cạnh `pyproject.toml`. Ý nghĩa từng phần:

| Thành phần | Vai trò |
|---|---|
| `modal.App("python-json-api-server")` | Khai báo app Modal |
| `modal.Volume.from_name(...)` | Volume lưu SQLite (`/data`), tạo tự động nếu chưa có |
| `Image.debian_slim(python_version="3.11")` | Image cơ bản, Python 3.11 |
| `pip_install_from_pyproject("pyproject.toml")` | Chỉ cài **dependencies** khai báo trong pyproject (không cài project) |
| `add_local_python_source("app")` | Đưa package `app` vào container để import được |
| `add_local_dir("public", "/root/public")` | Đưa thư mục `public` (favicon) vào `/root/public` — `app/routes/public.py` đọc file theo đường dẫn này |
| `Image.env({...})` | Env var cố định của image |
| `max_containers=1` | **Bắt buộc** khi dùng một file SQLite |
| `secrets=[...]` | Inject secret (chứa `ADMIN_KEY`) lúc runtime |
| `@modal.concurrent(max_inputs=20)` | Tối đa 20 request đồng thời trong một container |
| `scaledown_window=300` | Giữ container 5 phút sau request cuối để giảm cold start |
| `min_containers=1` (tùy chọn) | Luôn giữ một container ấm — tốn chi phí nhàn rỗi |
| `@modal.asgi_app()` | Biến function thành Web Function phục vụ ASGI app |

### 2.1. Biến môi trường — cái nào cần, cái nào không

Mọi biến cấu hình đều có **giá trị mặc định** trong `app/config.py` (`pydantic-settings`), nên chỉ cần set những biến khác mặc định:

| Biến | Cách xử lý trên Modal | Lý do |
|---|---|---|
| `APP_ENV` | `production` trong `Image.env()` | Đè default `development` |
| `DB_PATH` | `/data/data.db` trong `Image.env()` | Trỏ vào Volume |
| `RATE_LIMIT_ENABLED` | `true` trong `Image.env()` | Bật rate limiting |
| `ADMIN_KEY` | **trong Modal Secret** (không đặt trong image) | Là bí mật — không được bake vào image |
| `DEBUG_SQL`, `PORT` | Dùng default | `PORT` không dùng trên Modal |
| `REDIS_*` | Dùng default | Không có Redis → connect fail nhanh (timeout 5s) → fallback in-memory |
| `RATE_LIMIT_MAX/WINDOW_MS`, `DEFAULT_PAGE_SIZE`, `MAX_BODY_SIZE`, `SEED_API_BASE_URL` | Dùng default | Có thể đổi sau qua admin API |

> **Quan trọng:** Modal **inject Secret thành env var lúc runtime và đè lên env của image**. Vì vậy `ADMIN_KEY` chỉ cần nằm trong Secret.

## 3. Tạo Secret chứa `ADMIN_KEY`

```bash
modal secret create python-json-api-server-secrets \
  ADMIN_KEY="thay-bang-mot-secret-rat-dai"
```

`ADMIN_KEY` được hash (argon2) và lưu vào bảng `settings` **ở lần boot đầu tiên** (khi bảng `settings` còn trống). Phải tạo Secret **trước** lần chạy đầu.

> Sau khi database đã có dữ liệu, đổi giá trị trong Secret không xoay được khóa trong DB. Khi cần xoay khóa, dùng **admin API** `PATCH /api/admin/settings/ADMIN_KEY` trong lúc khóa cũ còn dùng được.

## 4. Chạy thử (development)

```bash
modal serve modal_app.py
```

- `modal serve` tạo **URL tạm** và hỗ trợ **hot reload** (thay đổi code tự cập nhật).
- Modal in ra URL dạng:
  ```
  https://<workspace>--python-json-api-server-web.modal.run
  ```

Kiểm tra nhanh:

```bash
curl https://<your-url>.modal.run/health
curl https://<your-url>.modal.run/api/users
```

Swagger UI: `https://<your-url>.modal.run/docs`

## 5. Deploy chính thức (production)

```bash
modal deploy modal_app.py
```

- `modal deploy` tạo **Web Function bền vững** với URL ổn định.
- Chạy lại lệnh này mỗi lần muốn cập nhật code.

## 6. Kiểm tra sau khi deploy

```bash
curl https://<workspace>--python-json-api-server-web.modal.run/health
curl https://<workspace>--python-json-api-server-web.modal.run/api/posts/1
curl https://<workspace>--python-json-api-server-web.modal.run/docs
```

**Warm-up:** gọi `/health` một lần sau khi deploy để cold start và seed hoàn tất trước khi dùng thật.

## Những lưu ý quan trọng

1. **Đừng bỏ `max_containers=1` khi còn dùng SQLite.** Dự án bật WAL (`PRAGMA journal_mode=WAL`), nhưng mọi dữ liệu vẫn nằm trong một file `.db` cùng các file WAL/SHM. Modal Volume không thiết kế cho nhiều container cùng sửa một file database; cơ chế đồng bộ là commit/reload, không có distributed file locking — dễ xảy ra "last write wins".
2. **Web Function chạy theo nhu cầu.** Khi không còn container hoạt động (mặc định sau ~5 phút idle), request kế tiếp phải chờ **cold start**. Nếu cần ổn định, bật `min_containers=1` — đổi lại phát sinh chi phí container nhàn rỗi.
3. **Lần boot đầu chậm hơn.** Với Volume mới, lifespan sẽ tạo database, nạp cấu hình và **seed ~1.300 bản ghi từ JSONPlaceholder**. Những lần sau database đã tồn tại nên seed bị bỏ qua (kiểm tra `COUNT(*)` trên bảng `User`).
4. **Rate limiter in-memory bị reset khi cold start.** Nếu container scale về 0 rồi khởi động lại, bộ đếm rate limit bị xóa — mỗi cold start lại được "toàn bộ" hạn mức. Chấp nhận được với lưu lượng thấp.
5. **Cửa sổ mất dữ liệu nhỏ với WAL.** Nếu container bị chấm dứt đột ngột, phần dữ liệu còn nằm trong file `-wal` chưa checkpoint có thể không được Volume snapshot lại. Với demo/personal API thì chấp nhận được.
6. **Chọn `ADMIN_KEY` trước lần boot đầu tiên** (xem mục 3).

## Khắc phục sự cố

| Triệu chứng | Nguyên nhân & cách xử lý |
|---|---|
| Request đầu rất chậm | Cold start + seed lần đầu. Gọi `/health` warm-up sau deploy |
| `/favicon.ico` trả 404 | Modal đặt `add_local_python_source("app")` khác `/root/app` → đường dẫn `/root/public` lệch. App vẫn chạy bình thường; chỉ cần chỉnh thư mục `public` cho khớp |
| Lỗi `Secret ... not found` | Chưa chạy `modal secret create` đúng tên `python-json-api-server-secrets` |
| Admin API trả 401 | `ADMIN_KEY` chưa đúng hoặc bị xoay; dùng admin API với khóa cũ để đổi |
| Rate limit "nhảy" sau mỗi lần cold start | Do limiter in-memory; xem lưu ý 4 |
| Lỗi khi build image từ Dockerfile | Modal không hỗ trợ lệnh `VOLUME`; dùng wrapper ASGI thay thế (xem bên dưới) |

## Vì sao không dùng Dockerfile hiện có?

Modal có `Image.from_dockerfile()`, nhưng Dockerfile của repo:

- Có lệnh `VOLUME ["/app/storage"]` — Modal Dockerfile builder **không hỗ trợ** lệnh này.
- Entrypoint chạy `python -m scripts.db_setup` trước khi `exec` process chính — làm phức tạp quy trình khởi động trên Modal.

Vì vậy, wrapper ASGI trong `modal_app.py` là cách đơn giản và phù hợp hơn.

## Khi nào nên chuyển sang kiến trúc lớn hơn

Kiến trúc hiện tại phù hợp cho **demo, API cá nhân, hoặc lưu lượng thấp**. Khi cần production với nhiều request ghi dữ liệu:

1. Chuyển SQLite → **PostgreSQL** (Neon/Supabase/RDS).
2. Bỏ `max_containers=1` để tận dụng autoscale của Modal.
3. Dùng **Redis** ngoài (Upstash/Memurai hoặc tương tự) để rate limit nhất quán giữa các container.
4. Đặt `min_containers` theo nhu cầu latency/cost.

## Tài liệu tham khảo

- [Web Functions — Modal Docs](https://modal.com/docs/guide/webhooks)
- [Secrets — Modal Docs](https://modal.com/docs/guide/secrets)
- [Volumes — Modal Docs](https://modal.com/docs/guide/volumes)
- [ASGI / FastAPI — Modal Docs](https://modal.com/docs/guide/asgi)
