# Hướng dẫn chạy Tests

> 🌐 Language / Ngôn ngữ: [English](TESTING.md) | **Tiếng Việt**

## Cài đặt dependency

```bash
pip install -e ".[dev]"
```

`pytest-cov`, `ruff`, và `mypy` đã bao gồm trong dev dependencies — coverage chạy tự động mỗi lần `pytest`.

## Quality Gates

Chạy các lệnh sau trước khi push:

```bash
ruff check .           # Kiểm tra lint
ruff format --check .  # Kiểm tra format
mypy app scripts       # Kiểm tra kiểu
pytest -v              # Tests + coverage
```

## Chạy tất cả tests + coverage

```bash
pytest -v
```

Mỗi lần chạy sẽ tự động in bảng coverage ở cuối terminal.

## Chạy tests theo file

```bash
pytest tests/test_resources.py -v        # CRUD routes
pytest tests/test_resources_extended.py -v  # Extended CRUD tests
pytest tests/test_admin.py -v            # Admin API
pytest tests/test_admin_extended.py -v   # Extended admin tests
pytest tests/test_health.py -v           # Health & Info
pytest tests/test_rate_limiter.py -v     # Rate limiter
pytest tests/test_rate_limiter_extended.py -v  # Extended rate limiter tests
pytest tests/test_auth_extended.py -v    # Auth middleware
pytest tests/test_main.py -v             # App entry point
pytest tests/test_redis_client.py -v     # Redis client
pytest tests/test_schemas.py -v          # Schema validation
pytest tests/test_services.py -v         # Services
pytest tests/test_public.py -v           # Favicon routes
pytest tests/test_scripts.py -v          # Script & dependency contracts
```

## Chạy tests theo class hoặc method

```bash
pytest tests/test_resources.py::TestCreatePost -v
pytest tests/test_resources.py::TestCreatePost::test_create_post -v
```

## Chạy tests với coverage

Coverage chạy **tự động** nhờ config trong `pyproject.toml`:

```toml
[tool.pytest.ini_options]
addopts = "--cov=app --cov-report=term-missing"
```

Chỉ cần:

```bash
pytest -v
```

Nếu muốn tắt coverage tạm thời:

```bash
pytest -v --no-cov
```

Tạo HTML report:

```bash
pytest --cov-report=html -v
# Kết quả trong thư mục htmlcov/
```

## Test Architecture

### Fixtures (`tests/conftest.py`)

| Fixture | Mô tả |
|---------|-------|
| `test_engine` | Tạo SQLite in-memory, auto drop_all khi kết thúc |
| `test_db` | AsyncSession từ test_engine |
| `seed_test_data` | Insert dữ liệu mẫu: 3 users, 5 posts, 5 comments, 2 albums, 5 photos, 5 todos, 3 settings |
| `test_app` | FastAPI test app với DB override, không dùng lifespan, include 5 routers (public, admin, health, info, resources) |
| `client` | `httpx.AsyncClient` kết nối test_app qua ASGI transport |

### Test Files (502 tests tổng cộng)

| File | Tests | Nội dung |
|------|-------|----------|
| `test_resources.py` | 57 | List, Get, Create, Update (PUT/PATCH), Delete, Nested routes, Filtering, Pagination, Search, Sort, 404 |
| `test_resources_extended.py` | 82 | Extended CRUD: tất cả resource types, edge cases, xử lý lỗi |
| `test_admin.py` | 27 | Truy cập trái phép, danh sách settings có xác thực, mask sensitive key, PATCH setting, reset database |
| `test_admin_extended.py` | 49 | Extended admin: cập nhật settings, reset database, mask settings, helper functions, Redis/rate limit updates |
| `test_admin_key.py` | 12 | Script `set_admin_key`: validate secret, cảnh báo, prompt tùy chọn, cập nhật env file |
| `test_auth_extended.py` | 19 | Auth cache (get/set/reset), kiểm tra admin auth, token validation |
| `test_config.py` | 3 | Container bootstrap settings: cờ seed demo và timeout mặc định/ghi đè |
| `test_container_config.py` | 26 | Dockerfile, cờ seed opt-in của entrypoint, smoke script contract |
| `test_health.py` | 9 | Health check, Redis status, danh sách tables, rate limit config, Info endpoints |
| `test_main.py` | 15 | App metadata, lifespan, powered-by middleware, print banner, persisted settings |
| `test_public.py` | 4 | Favicon routes (`.ico` và `.png`) |
| `test_rate_limiter.py` | 18 | Rate limit headers, exempt routes (`/health`), non-exempt routes |
| `test_rate_limiter_extended.py` | 62 | Extended rate limiter: IP normalization, CIDR match, circuit breaker, in-memory fallback, client IP extraction |
| `test_redis_client.py` | 26 | Redis client: connect, ping, eval, quit, reconnect, connected property |
| `test_schemas.py` | 24 | Pydantic schema validation cho tất cả models |
| `test_scripts.py` | 11 | Developer scripts, dependency contracts, lệnh startup seed có giới hạn |
| `test_services.py` | 58 | Seed data, seed settings, runtime config, database lifecycle |

### Rate Limiter Notes

- Bộ nhớ fallback (in-memory) là **per-process** — không đồng bộ giữa các workers.
- **Redis là bắt buộc nếu cần global rate limits** khi chạy nhiều workers hoặc processes.
- Phương thức `_InMemoryStore.increment()` dùng `asyncio.Lock` để đảm bảo atomic increments khi có concurrent requests.

### Key Points

- Tests chạy **in-memory SQLite** — không cần file DB hay Redis
- `pytest-asyncio` với `asyncio_mode = "auto"` — không cần `@pytest.mark.asyncio`
- DB seed data được reset tự động qua `test_engine` fixture
- Admin auth test dùng helper function `_set_admin_key_env()` để set env var `ADMIN_KEY=test-admin-key`
- Tổng cộng **502 tests**, coverage **100%** (1367 statements)

### Container Startup

Bootstrap container được kiểm tra bằng test entrypoint của `test_container_config.py` (với `python` giả) cùng smoke test Docker:

- Production/mặc định (`SEED_DATA_ON_STARTUP=false`): entrypoint migrate schema và seed local settings; **không bao giờ** gọi seed dữ liệu demo từ xa.
- Demo (`SEED_DATA_ON_STARTUP=true`): entrypoint migrate, seed settings, rồi chạy `scripts.db_seed_startup` có giới hạn thời gian trước khi server khởi động; timeout hoặc provider lỗi làm container thất bại.
- Giá trị true hợp lệ: `1`, `true`, `TRUE`, `yes`, `YES`. Giá trị false hợp lệ: `0`, `false`, `FALSE`, `no`, `NO`, rỗng/không đặt. Bất kỳ giá trị khác thoát với mã `2`.
- Dữ liệu mẫu cũng có thể được nạp tường minh bằng `./scripts/run.sh db:seed` như một lệnh bảo trì.

## Troubleshooting

**Tests fail với "database is locked"**
→ Chắc chắn đã cài `aiosqlite`. Kiểm tra: `pip show aiosqlite`

**Import error**
→ Chạy từ root project: `cd /path/to/Python-JSON-API-Server && pytest -v`

**Muốn thêm test mới**
→ Tạo file `tests/test_<name>.py`, import `client` fixture từ conftest. Ví dụ:
```python
import httpx


class TestMyFeature:
    async def test_something(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/users")
        assert resp.status_code == 200
```
