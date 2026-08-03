"""Modal wrapper for dangkhoa2016/Python-JSON-API-Server.

This file intentionally has a new filename and a new Modal App name so that
`modal serve` creates a new development endpoint instead of reusing the old
App/container identity.

Run from the repository root:

    modal serve modal_app.py
    modal deploy --strategy recreate --tag python-json-api-server-v1 modal_app.py

Revision: 2026-08-02
"""

from pathlib import Path

import modal

REVISION = "2026-08-02"

# A new App name produces a new Modal App identity and a new -dev URL.
APP_NAME = "python-json-api-server"

# Keep using the existing Secret and Volume so credentials and SQLite data are
# not lost merely because the wrapper/App name changed.
SECRET_NAME = "python-json-api-server-secrets"
VOLUME_NAME = "python-json-api-server-data"

DATABASE_MOUNT_PATH = "/data"
DATABASE_FILE = "/data/data.db"

# These paths are evaluated by the local Modal CLI while it prepares the Image.
SOURCE_ROOT = Path(__file__).resolve().parent
APP_SOURCE = SOURCE_ROOT / "app"
PUBLIC_SOURCE = SOURCE_ROOT / "public"

# The module is imported both locally and inside the remote Modal container.
# Only validate local repository files on the local side.
if modal.is_local():
    missing = [str(path) for path in (APP_SOURCE, PUBLIC_SOURCE) if not path.is_dir()]
    if missing:
        raise FileNotFoundError(
            "Missing project directories: "
            + ", ".join(missing)
            + ". Place this file in the repository root."
        )

app = modal.App(APP_NAME)

database_volume = modal.Volume.from_name(
    VOLUME_NAME,
    create_if_missing=True,
)

# Dependencies are explicit so pyproject.toml is not required in the remote
# container when Modal imports this wrapper.
PYTHON_DEPENDENCIES = (
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.34.0",
    "sqlalchemy[asyncio]>=2.0.0",
    "aiosqlite>=0.20.0",
    "redis[hiredis]>=5.0.0",
    "argon2-cffi>=23.1.0",
    "pydantic-settings>=2.0.0",
    "httpx>=0.27.0",
)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(*PYTHON_DEPENDENCIES)
    # copy=True bakes these directories into a new Image layer.
    .add_local_dir(APP_SOURCE, "/root/app", copy=True)
    .add_local_dir(PUBLIC_SOURCE, "/root/public", copy=True)
)


@app.function(
    image=image,
    env={
        "APP_ENV": "production",
        "DB_PATH": DATABASE_FILE,
        "RATE_LIMIT_ENABLED": "true",
        "PYTHONUNBUFFERED": "1",
        "MODAL_WRAPPER_REVISION": REVISION,
    },
    volumes={DATABASE_MOUNT_PATH: database_volume},
    secrets=[modal.Secret.from_name(SECRET_NAME)],
    # SQLite uses one writable database file, so do not scale to multiple
    # containers that could write concurrently.
    max_containers=1,
    # Scale down after at most five idle minutes.
    scaledown_window=5 * 60,
    # Allow initial table creation and data seeding to finish.
    timeout=15 * 60,
)
@modal.concurrent(max_inputs=10)
@modal.asgi_app(label="python-json-api-server")
def web():
    print(f"Starting Python JSON API Server wrapper {REVISION}", flush=True)

    from app.main import app as fastapi_app

    return fastapi_app
