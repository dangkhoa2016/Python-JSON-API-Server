from datetime import UTC, datetime

from argon2 import PasswordHasher
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, settings
from app.models import Setting

SETTING_DEFS = [
    {"key": "APP_ENV", "description": "Application environment (development, test, production)"},
    {"key": "PORT", "description": "HTTP server port number"},
    {"key": "DB_PATH", "description": "SQLite database file path"},
    {"key": "DEBUG_SQL", "description": "Enable SQL query logging to stderr"},
    {"key": "REDIS_HOST", "description": "Redis server hostname"},
    {"key": "REDIS_PORT", "description": "Redis server port"},
    {"key": "REDIS_DB", "description": "Redis database index"},
    {
        "key": "REDIS_URL",
        "description": "Full Redis connection URL (overrides host/port/db/password)",
    },
    {"key": "REDIS_PASSWORD", "description": "Redis server password"},
    {"key": "RATE_LIMIT_ENABLED", "description": "Enable rate limiting middleware"},
    {"key": "RATE_LIMIT_MAX", "description": "Maximum requests per rate-limit window"},
    {"key": "RATE_LIMIT_WINDOW_MS", "description": "Rate-limit window duration in milliseconds"},
    {
        "key": "DEFAULT_PAGE_SIZE",
        "description": "Default number of items per page in paginated responses",
    },
    {"key": "ADMIN_KEY", "description": "Admin authentication key (argon2-hashed on PATCH)"},
]


def default_setting_values(config: Settings) -> dict[str, str]:
    return {
        "APP_ENV": config.APP_ENV,
        "PORT": str(config.PORT),
        "DB_PATH": config.DB_PATH,
        "DEBUG_SQL": str(config.DEBUG_SQL).lower(),
        "REDIS_HOST": config.REDIS_HOST,
        "REDIS_PORT": str(config.REDIS_PORT),
        "REDIS_DB": str(config.REDIS_DB),
        "REDIS_URL": config.REDIS_URL or "",
        "REDIS_PASSWORD": config.REDIS_PASSWORD or "",
        "RATE_LIMIT_ENABLED": str(config.RATE_LIMIT_ENABLED).lower(),
        "RATE_LIMIT_MAX": str(config.RATE_LIMIT_MAX),
        "RATE_LIMIT_WINDOW_MS": str(config.RATE_LIMIT_WINDOW_MS),
        "DEFAULT_PAGE_SIZE": str(config.DEFAULT_PAGE_SIZE),
        "ADMIN_KEY": config.ADMIN_KEY,
    }


async def seed_settings(db: AsyncSession, config: Settings = settings) -> int:
    row = await db.execute(select(text("COUNT(*)")).select_from(Setting))
    count = row.scalar_one()
    if count > 0:
        print("[Settings] Already seeded, skipping.")
        return 0

    ph = PasswordHasher()
    now = datetime.now(UTC).isoformat()
    inserted = 0
    values = default_setting_values(config)

    for defn in SETTING_DEFS:
        val = values[defn["key"]]
        if defn["key"] == "ADMIN_KEY" and val:
            val = ph.hash(val)
        db.add(Setting(key=defn["key"], value=val, description=defn["description"], updated_at=now))
        inserted += 1

    await db.commit()
    print(f"[Seed] Seeded {inserted} settings from environment.")
    return inserted
