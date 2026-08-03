# Deploying to Modal.com

> 🌐 Language / Ngôn ngữ: **English** | [Tiếng Việt](DEPLOYMENT-ON-MODAL.COM.vi.md)

## Overview

This guide walks through deploying **Python JSON API Server** to [Modal.com](https://modal.com) as a **Web Function** (an HTTPS endpoint).

Deployment architecture:

- Wrap the existing `FastAPI` object (`app.main:app`) with `@modal.asgi_app()` instead of running Uvicorn as a traditional server. Modal fully supports ASGI and **ASGI lifespan** — so table creation, config loading, and data seeding still run as usual.
- Because the project uses **SQLite**, the whole service is pinned to a **single container** (`max_containers=1`). Data is kept in a **Modal Volume** so it survives restarts and cold starts.
- **Redis is optional.** When Redis is unavailable, the app falls back to an in-memory rate limiter.

## Prerequisites

- A [Modal.com](https://modal.com) account (free tier available).
- Python `>= 3.11`.
- The repository already has `modal_app.py` at the project root (branch `feat/modal-deploy`).

## 1. Install the Modal CLI

```bash
python -m pip install --upgrade modal
modal setup
```

`modal setup` opens a browser to sign in and stores the token on your machine.

## 2. Anatomy of `modal_app.py`

The file lives at the project root, next to `pyproject.toml`. Each part:

| Component | Role |
|---|---|
| `modal.App("python-json-api-server")` | Declares the Modal app |
| `modal.Volume.from_name(...)` | Volume that holds SQLite (`/data`), created automatically if missing |
| `Image.debian_slim(python_version="3.11")` | Base image, Python 3.11 |
| `pip_install_from_pyproject("pyproject.toml")` | Installs only the **dependencies** declared in pyproject (not the project itself) |
| `add_local_python_source("app")` | Copies the `app` package into the container so it can be imported |
| `add_local_dir("public", "/root/public")` | Copies the `public` directory (favicon) to `/root/public` — `app/routes/public.py` reads files from that path |
| `Image.env({...})` | Fixed environment variables baked into the image |
| `max_containers=1` | **Required** while the database is a single SQLite file |
| `secrets=[...]` | Injects the secret (holding `ADMIN_KEY`) at runtime |
| `@modal.concurrent(max_inputs=20)` | Up to 20 concurrent requests per container |
| `scaledown_window=300` | Keeps the container 5 minutes after the last request to reduce cold starts |
| `min_containers=1` (optional) | Always keeps one warm container — incurs idle cost |
| `@modal.asgi_app()` | Turns the function into a Web Function serving an ASGI app |

### 2.1. Environment variables — what is needed, what is not

Every config variable already has a **sensible default** in `app/config.py` (`pydantic-settings`), so only values that differ from the default need to be set:

| Variable | Handling on Modal | Reason |
|---|---|---|
| `APP_ENV` | `production` in `Image.env()` | Overrides the `development` default |
| `DB_PATH` | `/data/data.db` in `Image.env()` | Points into the Volume |
| `RATE_LIMIT_ENABLED` | `true` in `Image.env()` | Enables rate limiting |
| `ADMIN_KEY` | **in the Modal Secret** (never in the image) | It is a secret — do not bake it into the image |
| `DEBUG_SQL`, `PORT` | Use defaults | `PORT` is irrelevant on Modal |
| `REDIS_*` | Use defaults | No Redis → connection fails fast (5s timeout) → in-memory fallback |
| `RATE_LIMIT_MAX/WINDOW_MS`, `DEFAULT_PAGE_SIZE`, `MAX_BODY_SIZE`, `SEED_API_BASE_URL` | Use defaults | Can be changed later via the admin API |

> **Important:** Modal **injects Secrets as environment variables at runtime and they override image environment variables.** So `ADMIN_KEY` only needs to live in the Secret.

## 3. Create the Secret with `ADMIN_KEY`

```bash
modal secret create python-json-api-server-secrets \
  ADMIN_KEY="replace-with-a-long-secret"
```

`ADMIN_KEY` is hashed (argon2) and stored in the `settings` table on **first boot** (when the `settings` table is empty). Create the Secret **before** the first run.

> Once the database has data, changing the Secret value does not rotate the key stored in the DB. To rotate the key, use the **admin API** `PATCH /api/admin/settings/ADMIN_KEY` while the old key still works.

## 4. Run locally / development

```bash
modal serve modal_app.py
```

- `modal serve` creates a **temporary URL** with **hot reload** (code changes update automatically).
- Modal prints a URL like:
  ```
  https://<workspace>--python-json-api-server-web.modal.run
  ```

Quick checks:

```bash
curl https://<your-url>.modal.run/health
curl https://<your-url>.modal.run/api/users
```

Swagger UI: `https://<your-url>.modal.run/docs`

## 5. Production deploy

```bash
modal deploy modal_app.py
```

- `modal deploy` creates a **persistent Web Function** with a stable URL.
- Re-run this command each time you want to update the deployed code.

## 6. Verify after deploy

```bash
curl https://<workspace>--python-json-api-server-web.modal.run/health
curl https://<workspace>--python-json-api-server-web.modal.run/api/posts/1
curl https://<workspace>--python-json-api-server-web.modal.run/docs
```

**Warm-up:** call `/health` once after deploying so the cold start and seed finish before real use.

## Important notes

1. **Do not remove `max_containers=1` while using SQLite.** The project enables WAL (`PRAGMA journal_mode=WAL`), but all data still lives in a single `.db` file plus its WAL/SHM files. Modal Volume is not designed for multiple containers writing to one database file; its sync mechanism is commit/reload with no distributed file locking — "last write wins" can occur.
2. **Web Functions run on demand.** When no container is active (default ~5 minutes idle), the next request waits for a **cold start**. For steadier latency, enable `min_containers=1` — at the cost of idle container time.
3. **First boot is slower.** With a fresh Volume, the lifespan creates the database, loads config, and **seeds ~1,300 records from JSONPlaceholder**. Later boots skip seeding because the database already exists (checked via `COUNT(*)` on the `User` table).
4. **The in-memory rate limiter resets on cold start.** If the container scales to zero and restarts, the rate-limit counters are wiped — each cold start gets a fresh full quota. Acceptable for low traffic.
5. **Small data-loss window with WAL.** If the container is terminated abruptly, data still sitting in the `-wal` file that has not been checkpointed may not be snapshotted by the Volume. Acceptable for demos and personal APIs.
6. **Pick `ADMIN_KEY` before the first boot** (see section 3).

## Troubleshooting

| Symptom | Cause & fix |
|---|---|
| First request is very slow | Cold start + first-time seed. Call `/health` as a warm-up after deploy |
| `/favicon.ico` returns 404 | Modal placed `add_local_python_source("app")` somewhere other than `/root/app`, so the `/root/public` path is off. The app still works; just align the `public` directory path |
| `Secret ... not found` error | `modal secret create` was not run with the exact name `python-json-api-server-secrets` |
| Admin API returns 401 | `ADMIN_KEY` is wrong or rotated; use the admin API with the old key to change it |
| Rate limit "resets" after every cold start | In-memory limiter; see note 4 |
| Image build from the Dockerfile fails | Modal does not support the `VOLUME` instruction; use the ASGI wrapper instead (below) |

## Why not use the existing Dockerfile?

Modal offers `Image.from_dockerfile()`, but the repository Dockerfile:

- Contains `VOLUME ["/app/storage"]` — the Modal Dockerfile builder **does not support** this instruction.
- Runs `python -m scripts.db_setup` in its entrypoint before `exec`-ing the main process — an unnecessary complication on Modal.

The ASGI wrapper in `modal_app.py` is therefore simpler and better suited.

## When to move to a larger architecture

The current setup fits **demos, personal APIs, or low traffic**. For production with lots of write-heavy requests:

1. Move SQLite → **PostgreSQL** (Neon/Supabase/RDS).
2. Drop `max_containers=1` to take advantage of Modal autoscaling.
3. Use an external **Redis** (Upstash/Memurai or similar) for consistent rate limiting across containers.
4. Tune `min_containers` to your latency/cost trade-off.

## References

- [Web Functions — Modal Docs](https://modal.com/docs/guide/webhooks)
- [Secrets — Modal Docs](https://modal.com/docs/guide/secrets)
- [Volumes — Modal Docs](https://modal.com/docs/guide/volumes)
- [ASGI / FastAPI — Modal Docs](https://modal.com/docs/guide/asgi)
