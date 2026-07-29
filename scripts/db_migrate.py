"""Create missing tables from SQLAlchemy metadata."""

import scripts.env  # noqa: F401 — load .env before app imports
from app.database import engine
from app.models import Base


async def migrate() -> None:
    print("[Migrate] Creating missing tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("[Migrate] Schema initialization complete.")


async def _main() -> None:
    await migrate()


if __name__ == "__main__":
    import asyncio

    asyncio.run(_main())
