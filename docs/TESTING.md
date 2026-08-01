# Testing Guide

> 🌐 Language / Ngôn ngữ: **English** | [Tiếng Việt](TESTING.vi.md)

## Install Dependencies

```bash
pip install -e ".[dev]"
```

`pytest-cov`, `ruff`, and `mypy` are included in dev dependencies — coverage runs automatically every time `pytest` is executed.

## Quality Gates

Run these before pushing:

```bash
ruff check .           # Lint
ruff format --check .  # Check formatting
mypy app scripts       # Type check
pytest -v              # Tests + coverage
```

## Run All Tests + Coverage

```bash
pytest -v
```

Each run automatically prints the coverage table at the end of the terminal.

## Run Tests by File

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

## Run Tests by Class or Method

```bash
pytest tests/test_resources.py::TestCreatePost -v
pytest tests/test_resources.py::TestCreatePost::test_create_post -v
```

## Run Tests with Coverage

Coverage runs **automatically** thanks to the config in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
addopts = "--cov=app --cov-report=term-missing"
```

Simply run:

```bash
pytest -v
```

To temporarily disable coverage:

```bash
pytest -v --no-cov
```

Generate HTML report:

```bash
pytest --cov-report=html -v
# Output in the htmlcov/ directory
```

## Test Architecture

### Fixtures (`tests/conftest.py`)

| Fixture | Description |
|---------|-------------|
| `test_engine` | Creates in-memory SQLite, auto drop_all on teardown |
| `test_db` | AsyncSession from test_engine |
| `seed_test_data` | Inserts sample data: 3 users, 5 posts, 5 comments, 2 albums, 5 photos, 5 todos, 3 settings |
| `test_app` | FastAPI test app with DB override, no lifespan, includes 5 routers (public, admin, health, info, resources) |
| `client` | `httpx.AsyncClient` connected to test_app via ASGI transport |

### Test Files (502 tests total)

| File | Tests | Description |
|------|-------|-------------|
| `test_resources.py` | 57 | List, Get, Create, Update (PUT/PATCH), Delete, Nested routes, Filtering, Pagination, Search, Sort, 404 |
| `test_resources_extended.py` | 82 | Extended CRUD: all resource types, edge cases, error handling |
| `test_admin.py` | 27 | Unauthorized access, authorized settings list, sensitive key masking, PATCH setting, reset database |
| `test_admin_extended.py` | 49 | Extended admin: update settings, reset database, mask settings, helper functions, Redis/rate limit updates |
| `test_admin_key.py` | 12 | `set_admin_key` script: secret validation, warnings, optional prompt, env file update |
| `test_auth_extended.py` | 19 | Auth cache (get/set/reset), admin auth check, token validation |
| `test_config.py` | 3 | Container bootstrap settings: demo seed flag and timeout defaults/overrides |
| `test_container_config.py` | 26 | Dockerfile, entrypoint opt-in seed flag, smoke script contract |
| `test_health.py` | 9 | Health check, Redis status, tables list, rate limit config, Info endpoints |
| `test_main.py` | 15 | App metadata, lifespan, powered-by middleware, print banner, persisted settings |
| `test_public.py` | 4 | Favicon routes (`.ico` and `.png`) |
| `test_rate_limiter.py` | 18 | Rate limit headers, exempt routes (`/health`), non-exempt routes |
| `test_rate_limiter_extended.py` | 62 | Extended rate limiter: IP normalization, CIDR match, circuit breaker, in-memory fallback, client IP extraction |
| `test_redis_client.py` | 26 | Redis client: connect, ping, eval, quit, reconnect, connected property |
| `test_schemas.py` | 24 | Pydantic schema validation for all models |
| `test_scripts.py` | 11 | Developer scripts, dependency contracts, bounded startup seed command |
| `test_services.py` | 58 | Seed data, seed settings, runtime config, database lifecycle |

### Rate Limiter Notes

- The in-memory fallback state is **per-process** — it does not synchronize across workers.
- **Redis is required for global rate limits** when running multiple workers or processes.
- The `_InMemoryStore.increment()` method uses `asyncio.Lock` to guarantee atomic increments under concurrent requests.

### Key Points

- Tests run on **in-memory SQLite** — no need for a DB file or Redis
- `pytest-asyncio` with `asyncio_mode = "auto"` — no need for `@pytest.mark.asyncio`
- DB seed data is automatically reset via the `test_engine` fixture
- Admin auth tests use the helper function `_set_admin_key_env()` to set the env var `ADMIN_KEY=test-admin-key`
- Total **502 tests**, coverage **100%** (1367 statements)

### Container Startup

Container bootstrap is covered by `test_container_config.py` entrypoint tests (with a fake `python` executable) plus Docker smoke tests:

- Production/default (`SEED_DATA_ON_STARTUP=false`): the entrypoint migrates the schema and seeds local settings only; it never invokes the remote demo-data seed.
- Demo (`SEED_DATA_ON_STARTUP=true`): the entrypoint migrates, seeds settings, then runs the bounded `scripts.db_seed_startup` before the server starts; a timeout or provider failure fails the container.
- Accepted true values: `1`, `true`, `TRUE`, `yes`, `YES`. Accepted false values: `0`, `false`, `FALSE`, `no`, `NO`, empty/unset. Any other value exits `2`.
- Sample resource data can also be loaded explicitly with `./scripts/run.sh db:seed` as a maintenance command.

## Troubleshooting

**Tests fail with "database is locked"**
→ Make sure `aiosqlite` is installed. Check: `pip show aiosqlite`

**Import error**
→ Run from the project root: `cd /path/to/Python-JSON-API-Server && pytest -v`

**Adding new tests**
→ Create a file `tests/test_<name>.py`, import the `client` fixture from conftest. Example:
```python
import httpx


class TestMyFeature:
    async def test_something(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/users")
        assert resp.status_code == 200
```
