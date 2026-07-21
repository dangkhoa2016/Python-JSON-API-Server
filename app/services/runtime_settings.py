from collections.abc import Sequence
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Setting

KNOWN_KEYS = frozenset(
    {
        "APP_ENV",
        "PORT",
        "DB_PATH",
        "DEBUG_SQL",
        "REDIS_HOST",
        "REDIS_PORT",
        "REDIS_DB",
        "REDIS_URL",
        "REDIS_PASSWORD",
        "RATE_LIMIT_ENABLED",
        "RATE_LIMIT_MAX",
        "RATE_LIMIT_WINDOW_MS",
        "DEFAULT_PAGE_SIZE",
        "ADMIN_KEY",
    }
)

RATE_LIMIT_KEYS = frozenset({"RATE_LIMIT_ENABLED", "RATE_LIMIT_MAX", "RATE_LIMIT_WINDOW_MS"})
REDIS_KEYS = frozenset({"REDIS_HOST", "REDIS_PORT", "REDIS_DB", "REDIS_URL", "REDIS_PASSWORD"})


class InvalidRuntimeSetting(Exception):
    def __init__(self, detail: str, status_code: int = 400) -> None:
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


def parse_runtime_setting(key: str, value: object) -> str:
    if key not in KNOWN_KEYS:
        raise InvalidRuntimeSetting(f"Unknown setting key: {key}", status_code=404)

    if value is None or isinstance(value, (dict, list)):
        raise InvalidRuntimeSetting("Setting value must be a string or number")

    if key in ("RATE_LIMIT_ENABLED", "DEBUG_SQL"):
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, str) and value.lower() in ("true", "false"):
            return value.lower()
        raise InvalidRuntimeSetting(f"{key} must be true or false")

    if key in ("RATE_LIMIT_MAX", "RATE_LIMIT_WINDOW_MS"):
        try:
            if isinstance(value, str):
                parsed = int(value)
            elif isinstance(value, int):
                parsed = value
            else:
                raise InvalidRuntimeSetting(f"{key} must be an integer >= 1")
        except (ValueError, TypeError):
            raise InvalidRuntimeSetting(f"{key} must be an integer >= 1") from None
        if parsed < 1:
            raise InvalidRuntimeSetting(f"{key} must be >= 1")
        return str(parsed)

    if key == "REDIS_PORT":
        try:
            if isinstance(value, str):
                parsed = int(value)
            elif isinstance(value, int):
                parsed = value
            else:
                raise InvalidRuntimeSetting("REDIS_PORT must be an integer between 1 and 65535")
        except (ValueError, TypeError):
            msg = "REDIS_PORT must be an integer between 1 and 65535"
            raise InvalidRuntimeSetting(msg) from None
        if parsed < 1 or parsed > 65535:
            raise InvalidRuntimeSetting("REDIS_PORT must be between 1 and 65535")
        return str(parsed)

    if key == "REDIS_DB":
        try:
            if isinstance(value, str):
                parsed = int(value)
            elif isinstance(value, int):
                parsed = value
            else:
                raise InvalidRuntimeSetting("REDIS_DB must be a non-negative integer")
        except (ValueError, TypeError):
            raise InvalidRuntimeSetting("REDIS_DB must be a non-negative integer") from None
        if parsed < 0:
            raise InvalidRuntimeSetting("REDIS_DB must be >= 0")
        return str(parsed)

    raw = str(value)
    if not raw:
        if key in ("REDIS_URL", "REDIS_PASSWORD", "ADMIN_KEY"):
            return ""
        raise InvalidRuntimeSetting(f"{key} must not be empty")
    return raw


def rate_limit_values(rows: Sequence[Setting]) -> dict[str, str]:
    return {r.key: r.value for r in rows if r.key in RATE_LIMIT_KEYS}


def redis_values(rows: Sequence[Setting]) -> dict[str, str]:
    return {r.key: r.value for r in rows if r.key in REDIS_KEYS}


_settings_cache: dict[str, str] | None = None


async def load_settings_cache(db: AsyncSession) -> dict[str, str]:
    result = await db.execute(select(Setting))
    return {r.key: r.value for r in result.scalars().all()}


async def get_settings(db: AsyncSession) -> dict[str, str]:
    global _settings_cache
    if _settings_cache is None:
        _settings_cache = await load_settings_cache(db)
    return _settings_cache


async def reload_settings_cache(db: AsyncSession) -> dict[str, str]:
    global _settings_cache
    _settings_cache = await load_settings_cache(db)
    return _settings_cache


def reset_settings_cache() -> None:
    global _settings_cache
    _settings_cache = None


@dataclass
class RuntimeSettings:
    rate_limit: dict[str, str] = field(default_factory=dict)
    redis: dict[str, str] = field(default_factory=dict)
    debug_sql: bool = False


async def load_runtime_settings(db: AsyncSession) -> RuntimeSettings:
    cache = await get_settings(db)

    rate_limit = {}
    for key in RATE_LIMIT_KEYS:
        if key in cache:
            rate_limit[key] = parse_runtime_setting(key, cache[key])

    redis = {}
    for key in REDIS_KEYS:
        if key in cache:
            redis[key] = parse_runtime_setting(key, cache[key])

    debug_sql = (
        "DEBUG_SQL" in cache and parse_runtime_setting("DEBUG_SQL", cache["DEBUG_SQL"]) == "true"
    )

    return RuntimeSettings(rate_limit=rate_limit, redis=redis, debug_sql=debug_sql)


async def default_page_size(db: AsyncSession) -> int:
    raw = (await get_settings(db)).get("DEFAULT_PAGE_SIZE")
    if raw is None:
        return settings.DEFAULT_PAGE_SIZE
    try:
        parsed = int(raw)
    except (ValueError, TypeError):
        return settings.DEFAULT_PAGE_SIZE
    return parsed if parsed >= 1 else settings.DEFAULT_PAGE_SIZE
