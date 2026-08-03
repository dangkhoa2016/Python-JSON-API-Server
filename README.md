# Python JSON API Server

[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![CI](https://github.com/dangkhoa2016/Python-JSON-API-Server/actions/workflows/ci.yml/badge.svg)](https://github.com/dangkhoa2016/Python-JSON-API-Server/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> 🌐 Language / Ngôn ngữ: **English** | [Tiếng Việt](README.vi.md)

A JSONPlaceholder-compatible REST API built with **FastAPI**, **SQLAlchemy** (async SQLite), and optional **Redis** rate limiting — mirroring the full feature set of the Node.js version.

## Highlights

- **FastAPI + async SQLAlchemy** — Modern Python async stack with type-safe Pydantic schemas and automatic OpenAPI docs.
- **Multi-tier rate limiting** — Two-tier fallback: Redis (atomic Lua) → in-memory (LRU, 10k entries). Circuit breaker, CIDR-based trusted proxy extraction, and escalating block durations.
- **Docker-ready** — Multi-stage build, **non-root user**, automated DB setup on start, `.env` files excluded. SQLite data persists in a Docker volume.
- **Runtime configuration** — Update rate-limit and Redis settings via admin API **without restarting**. Changes take immediate effect through in-memory overrides.
- **Argon2 security** — Admin passwords hashed with argon2, results cached with 5s TTL and 1k-entry LRU. CRUD request bodies limited to 1 MB.
- **Cascade deletes** — Deleting a user removes their posts, albums, and todos. Deleting a post removes its comments. Deleting an album removes its photos.

## Technologies Used

- **Python >= 3.11** — runtime
- **FastAPI** — async web framework
- **SQLAlchemy 2.0** (async mode) — ORM with async SQLite via aiosqlite
- **aiosqlite** — async SQLite driver
- **Redis** (optional) — rate limiting via Lua scripts
- **argon2-cffi** — secure password hashing for admin authentication
- **pydantic-settings** — environment-based configuration
- **uvicorn** — ASGI server
- **pytest + httpx** — testing

## Requirements

- **Python >= 3.11**
- **Redis** (optional — rate limiting falls back to in-memory if unavailable)

## Quick Start

```bash
git clone <repo-url>
cd Python-JSON-API-Server

pip install -e ".[dev]"

./scripts/run.sh db:setup     # create tables + seed data (optional — the server also initializes the DB automatically on startup)
./scripts/run.sh start        # start server on http://localhost:3000
```

> The database commands are also available via direct Python invocation (e.g., `python -m scripts.db_setup`). See [Scripts](#scripts) for the full reference.

## Scripts

`run.sh` provides a unified CLI for database, server, and testing commands.

```bash
./scripts/run.sh <command>
```

### Database

| Command            | Description                                     |
|--------------------|-------------------------------------------------|
| `db:setup`         | Run migrate + seed + seed-settings (full setup) |
| `db:migrate`       | Create all 7 tables                             |
| `db:seed`          | Seed data from JSONPlaceholder                  |
| `db:seed-settings` | Seed default settings from environment          |
| `db:set-admin-key` | Set/rotate `ADMIN_KEY` in DB (writes `.env` in development) |

### Server

| Command | Description                                        |
|---------|----------------------------------------------------|
| `start` | Start uvicorn on port `$PORT` (default: 3000)      |
| `prod`  | Start in production mode (2 workers, no reload)    |
| `dev`   | Start with auto-reload on code changes             |

### Testing

| Command         | Description                                        |
|-----------------|----------------------------------------------------|
| `test`          | Run all tests                                      |
| `test:watch`    | Run tests in watch mode                            |
| `test:coverage` | Run tests + generate HTML report in `htmlcov/`     |

```bash
./scripts/run.sh test              # run all tests
./scripts/run.sh test -k "test_"   # pass extra args to pytest
./scripts/run.sh test:coverage     # generate HTML coverage report
```

## Docker

### Build

```bash
docker build -t python-json-api-server .
```

### Run

```bash
docker run -d -p 3000:3000 -v ./storage:/app/storage --name python-json-api-server python-json-api-server
```

The container entrypoint runs in a fixed order:

1. Migrate the schema.
2. Seed local application settings.
3. Seed remote demo data — only when `SEED_DATA_ON_STARTUP=true`.
4. Start the server command.

| Mode | `SEED_DATA_ON_STARTUP` | Result |
|---|---:|---|
| Production/default | `false` | Migrate and seed local settings only; never call the external sample provider. |
| Demo | `true` | Migrate, seed settings, then idempotently seed sample data before the server starts. |

A demo deployment with the flag enabled **fails visibly** if the sample-data seed times out or the provider errors — it never starts as an empty "successful" demo. The opt-in seed runs within a single total timeout of `SEED_TIMEOUT_SECONDS` (default `60`).

#### Demo (with sample data)

```bash
docker run -d -p 3000:3000 \
  -e SEED_DATA_ON_STARTUP=true \
  -e SEED_TIMEOUT_SECONDS=60 \
  -v ./storage:/app/storage \
  --name python-json-api-server-demo python-json-api-server
```

For deployments that manage their own data, operators can seed or re-seed sample resources explicitly with `python -m scripts.db_seed` (or `./scripts/run.sh db:seed`) — a maintenance command, not a required post-deploy step.

### Environment Variables

```bash
docker run -d -p 3000:3000 \
  -e ADMIN_KEY=my-secret-key \
  -e REDIS_HOST=redis \
  -v ./storage:/app/storage \
  --name python-json-api-server python-json-api-server
```

### Notes

- The container runs as a non-root `app` user.
- Database files persist in `/app/storage` (declared as a `VOLUME`). Data is preserved across restarts; when the demo seed is enabled it is skipped automatically if the resource data already exists.
- `.env` and `.env.*` files are **excluded** by `.dockerignore` and are **not copied** into the image.
- The entrypoint migrates the schema and seeds local settings, then seeds remote demo data only when `SEED_DATA_ON_STARTUP=true`.
- The container always listens on port `3000` (hardcoded in the image) — the `PORT` environment variable only applies to `./scripts/run.sh` runs outside of Docker.

---

## Configuration

All configuration is loaded from environment variables (with `.env` file support in development via pydantic-settings).

### Variables

| Variable               | Default     | Description                            |
|------------------------|-------------|----------------------------------------|
| `APP_ENV`               | `development` | Application environment                |
| `DEBUG_SQL`             | `false`       | Enable SQL query logging               |
| `PORT`                 | `3000`      | Server port                            |
| `DB_PATH`              | `./storage/data.db` | SQLite database file path      |
| `REDIS_URL`            | _(none)_    | Redis connection URL (takes priority). Format: `redis://user:password@host:port/db` |
| `REDIS_HOST`           | `127.0.0.1` | Redis host                             |
| `REDIS_PORT`           | `6379`      | Redis port                             |
| `REDIS_DB`             | `0`         | Redis database index                   |
| `REDIS_PASSWORD`       | _(none)_    | Redis password (for `AUTH`)            |
| `RATE_LIMIT_ENABLED`   | `true`      | Enable/disable rate limiting           |
| `RATE_LIMIT_MAX`       | `100`       | Max requests per time window           |
| `RATE_LIMIT_WINDOW_MS` | `60000`     | Time window in milliseconds (default 1 min) |
| `TRUSTED_PROXIES`      | `127.0.0.1,::1` | Comma-separated IPs/CIDRs allowed to set `X-Forwarded-For`/`X-Real-IP` (e.g. `10.0.0.0/8`) |
| `SEED_API_BASE_URL`    | `https://jsonplaceholder.typicode.com` | Base URL for seed data API |
| `SEED_DATA_ON_STARTUP` | `false` | Seed remote demo data during container startup (container bootstrap control, not a runtime setting) |
| `SEED_TIMEOUT_SECONDS` | `60` | Total timeout for the opt-in demo-data seed; the container fails if it expires |
| `MAX_BODY_SIZE`        | `1048576`   | Max CRUD request body size in bytes |
| `DEFAULT_PAGE_SIZE`   | `10`        | Default number of results per page for `_page`/`_limit` pagination |
| `MAX_PAGE_SIZE`       | `100`       | Maximum number of results returned per request |
| `ADMIN_KEY`           | `""`        | Master key to authenticate admin API requests (Bearer token) |
| **Runtime updates**   | —           | Patching `RATE_LIMIT_ENABLED`, `RATE_LIMIT_MAX`, `RATE_LIMIT_WINDOW_MS`, `DEBUG_SQL`, `DEFAULT_PAGE_SIZE`, `REDIS_URL`, `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB`, or `REDIS_PASSWORD` via the admin API applies changes immediately — no server restart needed |

---

## API Endpoints

### Resources

| Method   | Path                        | Description                  |
|----------|-----------------------------|------------------------------|
| `GET`    | `/api/users`                | List all users               |
| `GET`    | `/api/users/:id`            | Get user by ID               |
| `GET`    | `/api/users/:id/posts`      | Posts by user                |
| `GET`    | `/api/users/:id/albums`     | Albums by user               |
| `GET`    | `/api/users/:id/todos`      | Todos by user                |
| `GET`    | `/api/posts`                | List all posts               |
| `GET`    | `/api/posts/:id`            | Get post by ID               |
| `GET`    | `/api/posts/:id/comments`   | Comments on post             |
| `GET`    | `/api/comments`             | List all comments            |
| `GET`    | `/api/albums`               | List all albums              |
| `GET`    | `/api/albums/:id/photos`    | Photos in album              |
| `GET`    | `/api/photos`               | List all photos              |
| `GET`    | `/api/todos`                | List all todos               |
| `POST`   | `/api/:table`               | Create a new resource        |
| `PUT`    | `/api/:table/:id`           | Replace resource entirely    |
| `PATCH`  | `/api/:table/:id`           | Partial update               |
| `DELETE` | `/api/:table/:id`           | Delete resource              |

> **Cascade deletes**: Deleting a `user` removes their `posts`, `albums`, and `todos`. Deleting a `post` removes its `comments`. Deleting an `album` removes its `photos`.

> **Body contract**: All `POST`, `PUT`, and `PATCH` requests must have a JSON object body. Non-object bodies (`null`, array, string, number, empty) are rejected with `400 Bad Request`. `POST` creates a new resource (missing fields use defaults). `PUT` performs a full replacement — all fields are written from the request body, and unspecified fields are set to their default values. `PATCH` performs a partial update — only the specified fields are changed.

> **Note**: The `settings` table is **not** exposed via the generic CRUD endpoints — `/api/settings` returns `404`. Settings can only be read and updated through the admin API (`GET /api/admin/settings`, `PATCH /api/admin/settings/:key`).

> **Note**: Write endpoints (`POST`, `PUT`, `PATCH`, `DELETE`) are intentionally open — anyone can create, overwrite, or delete resources, mirroring JSONPlaceholder semantics. Data is not durable; reset it anytime via the admin reset endpoint (`POST /api/admin/reset-database`).

### Query String Filtering & Pagination

```bash
# Filter posts by userId
GET /api/posts?userId=1

# Filter todos by userId and completed status
GET /api/todos?userId=1&completed=false

# Filter comments by postId
GET /api/comments?postId=1
```

Filterable columns vary by table (e.g., `title`, `email`, `username`). The `completed` field accepts `true`/`false` strings.

### Pagination

| Param     | Description                                    | Example                      |
|-----------|------------------------------------------------|------------------------------|
| `_page`   | Page number (1-based), used with `_limit`      | `?_page=1&_limit=10`        |
| `_limit`  | Items per page (default: `DEFAULT_PAGE_SIZE`)  | `?_page=2&_limit=5`         |
| `_start`  | Offset index for slicing                       | `?_start=10&_end=20`        |
| `_end`    | End index (exclusive) for slicing              | `?_start=0&_end=5`          |

`_limit` is capped at `MAX_PAGE_SIZE` (default 100), and when both `_start` and `_end` are given the window is capped as well. Note that `_start` alone (without `_end`) is not capped — it returns every row from that offset onward.

### Search

Search across text columns using the `q` parameter. Searchable columns vary by table:

| Table      | Searchable columns                        |
|------------|-------------------------------------------|
| `users`    | `name`, `username`, `email`               |
| `posts`    | `title`, `body`                           |
| `comments` | `name`, `email`, `body`                   |
| `albums`   | `title`                                   |
| `photos`   | `title`                                   |
| `todos`    | `title`                                   |

```bash
# Search posts by title or body
GET /api/posts?q=first

# Combine search with filter
GET /api/posts?q=Post&userId=1

# Search todos
GET /api/todos?q=groceries
```

### Sorting

| Param    | Values         | Description                          |
|----------|----------------|--------------------------------------|
| `_sort`  | column name    | Column to sort by                    |
| `_order` | `asc` / `desc` | Sort direction (default: `asc`)      |

```bash
# Sort posts by title ascending
GET /api/posts?_sort=title&_order=asc

# Sort posts by title descending
GET /api/posts?_sort=title&_order=desc

# Combine sort with pagination
GET /api/posts?_sort=id&_order=desc&_limit=2
```

### System Endpoints

| Path                              | Description                          |
|-----------------------------------|--------------------------------------|
| `GET /`                           | API info with available endpoints    |
| `GET /api`                        | API info (same as above)             |
| `GET /health`                     | Server status (DB, Redis, tables, rate limit config) |
| `GET /api/health`                 | Same as above                        |
| `GET /docs`                       | Interactive API docs (Swagger UI)    |
| `GET /redoc`                      | ReDoc API docs                       |
| `GET /openapi.json`               | OpenAPI schema                       |
| `GET /favicon.ico`                | Favicon (not in OpenAPI schema)      |
| `GET /favicon.png`                | Favicon PNG (not in OpenAPI schema)  |
| `GET /api/admin/settings`         | List all settings (requires auth)    |
| `PATCH /api/admin/settings/:key`  | Update a setting value — rate-limit & Redis changes take **immediate effect** at runtime (requires auth) |
| `POST /api/admin/reset-database`  | Clear data tables and re-seed from JSONPlaceholder (requires auth) |

### Admin API

Admin endpoints are protected by Bearer token authentication using the `ADMIN_KEY` environment variable. Settings values are stored in the `settings` database table.

```bash
# List all settings
curl http://localhost:3000/api/admin/settings \
  -H "Authorization: Bearer my-secret-key"

# Update a setting
curl -X PATCH http://localhost:3000/api/admin/settings/ADMIN_KEY \
  -H "Authorization: Bearer my-secret-key" \
  -H "Content-Type: application/json" \
  -d '{"value": "new-secret-key"}'

# Reset database (clears all data and re-fetches from JSONPlaceholder)
curl -X POST http://localhost:3000/api/admin/reset-database \
  -H "Authorization: Bearer my-secret-key" \
  -H "Content-Type: application/json" \
  -d '{"confirm": true}'
```

The `ADMIN_KEY` is hashed with **argon2** before storage. When updating the password via `PATCH /api/admin/settings/ADMIN_KEY`, the new value is automatically hashed. Passwords are never stored in plaintext.

**Bootstrapping / rotating `ADMIN_KEY`:** Admin authentication has two sources of truth — the `ADMIN_KEY` **environment variable** (or `.env` in development) acts as a master switch (admin APIs are disabled while it is empty), and the **`settings` table** stores the argon2-hashed credential that Bearer tokens are verified against. On first start with a fresh database, the settings seed copies the env value (hashed) into that table.

As a result, a server started with an empty `ADMIN_KEY` is locked out of the admin API — even after seeding, because seeding only records what the environment provided. To set or rotate the key without deleting the database:

```bash
./scripts/run.sh db:set-admin-key my-new-secret-key
```

Omit the argument to enter the secret interactively without echo:
```bash
./scripts/run.sh db:set-admin-key
ADMIN_KEY: (typed, not echoed)
```

This hashes the value and upserts it into the `settings` table. In development it also writes `ADMIN_KEY` into `.env`, so the auth gate passes on the next start — restart the server after running it. The key must be non-empty and contain no whitespace; a warning is printed when it is shorter than 12 characters. In non-development environments, the CLI only updates the database — set the `ADMIN_KEY` env var yourself.

**Runtime configuration updates**: When patching rate-limit settings (`RATE_LIMIT_ENABLED`, `RATE_LIMIT_MAX`, `RATE_LIMIT_WINDOW_MS`), logging or pagination settings (`DEBUG_SQL`, `DEFAULT_PAGE_SIZE`), or Redis connection settings (`REDIS_HOST`, `REDIS_PORT`, `REDIS_DB`, `REDIS_PASSWORD`, `REDIS_URL`), the server applies the changes immediately — no restart required.

Argon2 verification results are **cached in-memory for 5 seconds** per token, avoiding repeated hashing on consecutive admin requests. On error, the result is also cached as invalid — preventing timing or error-message side-channel leaks.

---

## Response Headers

Responses include CORS and rate-limit headers:

```
Access-Control-Allow-Origin: *                 ← present only when the request carries an Origin header (browser/CORS)
X-RateLimit-Limit:     100                     ← per-method: 100 (GET/HEAD), 50 (POST/PUT/PATCH), 33 (DELETE)
X-RateLimit-Remaining: 99
X-RateLimit-Reset:     <epoch seconds>         ← absolute Unix timestamp of the window/block expiry
X-RateLimit-Store:     redis                   ← "redis" or "memory"
```

The `X-RateLimit-*` headers are sent only when rate limiting is enabled, the request hits a rate-limited route (not `/health`, `/api/health`, or `/favicon.ico`), and the client IP can be determined.

When the rate limit is exceeded, a `429 Too Many Requests` response is returned with a `Retry-After` header:

```
X-RateLimit-Limit:     100
X-RateLimit-Remaining: 0
X-RateLimit-Reset:     <epoch seconds>         ← absolute Unix timestamp when the block expires
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

> **Multi-worker note:** the in-memory rate-limit store is per-process. When running multiple uvicorn workers (`./scripts/run.sh prod`, which uses 2 workers), counts are not shared between workers. For consistent global limits across workers, point `REDIS_URL` (or the `REDIS_HOST`/`REDIS_PORT` settings) at a shared Redis instance.

---

## Examples

```bash
# List users
curl http://localhost:3000/api/users

# Create a new post
curl -X POST http://localhost:3000/api/posts \
  -H "Content-Type: application/json" \
  -d '{"userId": 1, "title": "Hello", "body": "World"}'

# Partial update
curl -X PATCH http://localhost:3000/api/posts/1 \
  -H "Content-Type: application/json" \
  -d '{"title": "Updated title"}'

# Delete
curl -X DELETE http://localhost:3000/api/posts/1

# Health check
curl http://localhost:3000/health
```

## Database

- **7 tables:** `users`, `posts`, `comments`, `albums`, `photos`, `todos`, `settings`
- **WAL mode** for better concurrent read performance
- **Foreign keys** enforced via `PRAGMA foreign_keys=ON`
- **Seed data** fetched from [JSONPlaceholder](https://jsonplaceholder.typicode.com) on first run:
  - 10 users (with `address` and `company` stored as JSON, parsed on read)
  - 100 posts
  - 500 comments
  - 100 albums
  - 5000 photos
  - 200 todos
  - 14 settings (environment variables)

### Database Scripts

| Script        | Command                          | Description                                           |
|---------------|----------------------------------|-------------------------------------------------------|
| `db:setup`    | `./scripts/run.sh db:setup`              | Runs migrate + seed + seed-settings                   |
| `db:migrate`  | `./scripts/run.sh db:migrate`            | Creates the 7 tables                                  |
| `db:seed`     | `./scripts/run.sh db:seed`               | Seed data from JSONPlaceholder                        |

---

## Testing

Uses **pytest** with **pytest-asyncio** for async test support and **httpx** for HTTP client testing.

```bash
./scripts/run.sh test              # Run all tests (coverage shown via pyproject.toml addopts)
./scripts/run.sh test -v           # Verbose output
./scripts/run.sh test -k "test_"   # Run specific tests
./scripts/run.sh test:coverage     # Generate HTML coverage report in htmlcov/
```

## Similar Projects

- [Nodejs-JSON-API-Server](https://github.com/dangkhoa2016/Nodejs-JSON-API-Server) — The original Node.js implementation using only built-in modules, with the same feature set.
- [JSON-API-Server-With-Dashboard-UI](https://github.com/dangkhoa2016/JSON-API-Server-With-Dashboard-UI) — Extended version with a built-in dashboard UI for managing data and monitoring the API.

## Runtime Settings

14 settings are persisted in the `settings` table and loaded at startup:

| Key | Default | Type | Description |
|---|---|---|---|
| `APP_ENV` | `development` | string | Application environment |
| `PORT` | `3000` | int | HTTP server port |
| `DB_PATH` | `./storage/data.db` | string | SQLite database path |
| `DEBUG_SQL` | `false` | bool | Enable SQL query logging |
| `REDIS_HOST` | `127.0.0.1` | string | Redis server hostname |
| `REDIS_PORT` | `6379` | int | Redis server port |
| `REDIS_DB` | `0` | int | Redis database index |
| `REDIS_URL` | _(empty)_ | string | Full Redis URL (overrides host/port/db) |
| `REDIS_PASSWORD` | _(empty)_ | string | Redis password |
| `RATE_LIMIT_ENABLED` | `true` | bool | Enable rate limiting |
| `RATE_LIMIT_MAX` | `100` | int | Max requests per window |
| `RATE_LIMIT_WINDOW_MS` | `60000` | int | Window duration in ms |
| `DEFAULT_PAGE_SIZE` | `10` | int | Pagination page size |
| `ADMIN_KEY` | _(empty)_ | string | Admin auth key (argon2-hashed) |

Settings are seeded from the pydantic `Settings` object on first start with a fresh database, so environment variables and the `.env` file take precedence over the typed defaults shown above. On subsequent starts, seeding is skipped if the `settings` table is already populated. The admin API can update them at runtime without restart. The `ADMIN_KEY` can also be set or rotated outside the API via `./scripts/run.sh db:set-admin-key` (with the secret as an argument, or entered interactively without echo) — in development this also updates `.env`.

## Docker

```bash
# Build and run with fresh SQLite volume
./scripts/container_smoke.sh python-json-api-server:smoke
```

The smoke script creates a fresh Docker volume on every invocation, starts the container, polls the `/health` endpoint (30-second timeout), and cleans up on exit. No prior Docker state is reused.

## Documentation

- [Deploying to Modal.com](docs/DEPLOYMENT-ON-MODAL.COM.md)

## License

[MIT](LICENSE)
