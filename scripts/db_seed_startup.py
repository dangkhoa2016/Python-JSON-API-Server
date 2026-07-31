"""Seed demo data during container startup within one total timeout."""

import asyncio
import sys

import scripts.env  # noqa: F401 — load .env before app imports
from app.config import settings
from app.database import async_session, init_db
from app.services.seed import seed


async def seed_for_startup(timeout_seconds: float) -> int:
    """Initialize the database and seed demo data within one total timeout."""
    if timeout_seconds <= 0:
        raise ValueError(f"timeout_seconds must be positive, got {timeout_seconds}")
    async with asyncio.timeout(timeout_seconds):
        await init_db()
        async with async_session() as db:
            return await seed(db)


def main() -> int:
    """Run bounded startup seeding and return a process exit code."""
    timeout = settings.SEED_TIMEOUT_SECONDS
    try:
        count = asyncio.run(seed_for_startup(timeout))
    except TimeoutError:
        print(f"[Seed] Demo data seed timed out after {timeout}s", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"[Seed] Demo data seed failed ({type(exc).__name__})", file=sys.stderr)
        return 1
    print(f"[Seed] Seeded {count} demo rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
