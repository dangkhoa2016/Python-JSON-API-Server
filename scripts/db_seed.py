"""Seed posts, comments, albums, photos, todos from JSONPlaceholder."""

import asyncio

from app.database import async_session, init_db
from app.services.seed import seed


async def main() -> None:
    await init_db()
    async with async_session() as db:
        await seed(db)


if __name__ == "__main__":
    asyncio.run(main())
