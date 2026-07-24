from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text

from app.routes.resources import PUBLIC_TABLES as TABLES
from app.services.runtime_config import RateLimitConfig

router = APIRouter()


async def _get_redis_client(request: Request) -> Any:
    return getattr(request.app.state, "redis_client", None)


async def _get_rate_limit_config(request: Request) -> RateLimitConfig:
    return getattr(
        request.app.state,
        "rate_limit_config",
        RateLimitConfig(enabled=True, max_requests=100, window_ms=60000),
    )


async def _get_db_engine(request: Request) -> Any:
    return getattr(request.app.state, "db_engine", None)


async def _probe_db(db_engine: Any) -> bool:
    if db_engine is None:
        return False
    try:
        async with db_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@router.get("/health")
@router.get("/api/health")
async def health(
    redis_client: Any = Depends(_get_redis_client),  # noqa: B008
    rate_limit_config: RateLimitConfig = Depends(_get_rate_limit_config),  # noqa: B008
    db_engine: Any = Depends(_get_db_engine),  # noqa: B008
) -> dict[str, Any]:
    redis_status = "connected"
    if not redis_client or not getattr(redis_client, "connected", False):
        redis_status = "disconnected"

    db_status = "connected" if await _probe_db(db_engine) else "disconnected"

    return {
        "status": "ok" if db_status == "connected" else "degraded",
        "redis": redis_status,
        "db": db_status,
        "tables": TABLES,
        "rateLimit": {
            "enabled": rate_limit_config.enabled,
            "max": rate_limit_config.max_requests,
            "windowMs": rate_limit_config.window_ms,
        },
    }
