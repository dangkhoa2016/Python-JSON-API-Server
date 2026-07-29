"""Seed default application settings."""

import asyncio

import scripts.env  # noqa: F401 — load .env before app imports
from app.database import async_session, init_db
from app.services.seed_settings import seed_settings


async def main() -> None:
    await init_db()
    async with async_session() as db:
        await seed_settings(db)


if __name__ == "__main__":
    asyncio.run(main())
