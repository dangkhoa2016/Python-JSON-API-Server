"""Set or rotate the ADMIN_KEY setting in the database."""

import asyncio
import getpass
import sys
from pathlib import Path

import scripts.env  # noqa: F401 — load .env before app imports
from app.config import settings
from app.database import async_session, init_db
from app.services.env_file import update_env_file
from app.services.seed_settings import set_admin_key

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
MIN_LENGTH = 12


def validate_secret(key: str) -> str | None:
    if not key:
        return "ADMIN_KEY must not be empty"
    if any(c.isspace() for c in key):
        return "ADMIN_KEY must not contain whitespace"
    return None


def secret_warning(key: str) -> str | None:
    if len(key) < MIN_LENGTH:
        return f"ADMIN_KEY is shorter than {MIN_LENGTH} characters."
    return None


def read_secret(argument: str | None) -> str:
    if argument is not None:
        return argument
    return getpass.getpass("ADMIN_KEY: ")


async def apply_admin_key(secret: str) -> None:
    await init_db()
    async with async_session() as db:
        await set_admin_key(db, secret)
    print("[Admin] ADMIN_KEY updated in database.")
    if settings.APP_ENV == "development":
        update_env_file(ENV_FILE, "ADMIN_KEY", secret)
        print(f"[Admin] ADMIN_KEY written to {ENV_FILE} — restart the server to apply.")
    else:
        print(
            "[Admin] Non-development environment: "
            "set the ADMIN_KEY env var before starting the server."
        )


def main() -> int:
    if len(sys.argv) > 2:
        print("Usage: python -m scripts.set_admin_key [admin-secret]")
        print("Omit admin-secret to enter it without echo.")
        return 2
    argument = sys.argv[1] if len(sys.argv) == 2 else None
    secret = read_secret(argument)
    err = validate_secret(secret)
    if err is not None:
        print(f"Error: {err}")
        return 1
    warning = secret_warning(secret)
    if warning is not None:
        print(f"[Warning] {warning}")
    asyncio.run(apply_admin_key(secret))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
