"""Initialize schema, then seed data."""

import scripts.env  # noqa: F401 — load .env before app imports
from app.database import async_session, init_db
from app.services.seed import seed
from app.services.seed_settings import seed_settings
from scripts.db_migrate import migrate


async def setup() -> None:
    await init_db()
    await migrate()
    async with async_session() as db:
        await seed(db)
    async with async_session() as db:
        await seed_settings(db)
    print("[Setup] Database setup complete.")


async def _main() -> None:
    await setup()


if __name__ == "__main__":
    import asyncio

    asyncio.run(_main())
