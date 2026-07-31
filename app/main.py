from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import async_session, engine, init_db
from app.middleware.rate_limiter import create_rate_limiter
from app.middleware.trailing_slash import StripTrailingSlashMiddleware
from app.models import Base
from app.redis_client import RedisClient
from app.routes.admin import router as admin_router
from app.routes.health import router as health_router
from app.routes.info import router as info_router
from app.routes.public import router as public_router
from app.routes.resources import router as resources_router
from app.services.runtime_config import RateLimitConfig
from app.services.runtime_settings import load_runtime_settings
from app.services.seed_settings import seed_settings

logger = logging.getLogger(__name__)

redis_client = RedisClient()

rate_limit_config = RateLimitConfig(
    enabled=settings.RATE_LIMIT_ENABLED,
    max_requests=settings.RATE_LIMIT_MAX,
    window_ms=settings.RATE_LIMIT_WINDOW_MS,
)

RateLimiterMiddleware = create_rate_limiter(redis_client, rate_limit_config)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    await init_db()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as db:
        await seed_settings(db)

        rt = await load_runtime_settings(db)

        rl = rt.rate_limit
        rate_limit_config.update(
            {
                "enabled": rl.get("RATE_LIMIT_ENABLED", "true") == "true",
                "max": int(rl.get("RATE_LIMIT_MAX", 100)),
                "windowMs": int(rl.get("RATE_LIMIT_WINDOW_MS", 60000)),
            }
        )
        engine.echo = rt.debug_sql

        redis_vals = rt.redis
        if redis_vals.get("REDIS_URL"):
            redis_opts: dict = {"url": redis_vals["REDIS_URL"]}
        else:
            redis_opts = {
                "host": redis_vals.get("REDIS_HOST", "127.0.0.1"),
                "port": int(redis_vals.get("REDIS_PORT", 6379)),
                "db": int(redis_vals.get("REDIS_DB", 0)),
                "password": redis_vals.get("REDIS_PASSWORD"),
            }

        await redis_client.connect(redis_opts)
        if redis_client.connected:
            logger.info("[Redis] Connected")
        else:
            logger.warning("[Redis] Unavailable — rate limiting falls back to in-memory")

    app.state.redis_client = redis_client
    app.state.rate_limit_config = rate_limit_config
    app.state.db_engine = engine

    print_banner()

    yield

    try:
        await redis_client.quit()
    except Exception:
        pass


app = FastAPI(
    title="python-json-api-server",
    version="1.0.0",
    lifespan=lifespan,
)


app.add_middleware(StripTrailingSlashMiddleware)
app.add_middleware(RateLimiterMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

app.include_router(public_router)
app.include_router(health_router)
app.include_router(info_router)
app.include_router(admin_router)
app.include_router(resources_router)


def print_banner() -> None:
    port = settings.PORT
    rl_text = (
        f"  Rate limit: {settings.RATE_LIMIT_MAX} req / {settings.rate_limit_window_sec}s "
        f"({'Redis' if redis_client.connected else 'Memory'})"
    ).ljust(50)
    print(f"""
╔══════════════════════════════════════════════════╗
║          python-json-api-server v1.0.0           ║
╠══════════════════════════════════════════════════╣
║  http://localhost:{port}{" " * (31 - len(str(port)))}║
║                                                  ║
║  Endpoints:                                      ║
║    GET    /api/users                             ║
║    GET    /api/users/:id                         ║
║    GET    /api/users/:id/posts                   ║
║    GET    /api/posts                             ║
║    GET    /api/posts/:id                         ║
║    GET    /api/posts/:id/comments                ║
║    GET    /api/comments                          ║
║    GET    /api/albums                            ║
║    GET    /api/albums/:id/photos                 ║
║    GET    /api/photos                            ║
║    GET    /api/todos                             ║
║    POST/PUT/PATCH/DELETE on any resource         ║
║    GET    /health                                ║
║                                                  ║
║{rl_text}║
╚══════════════════════════════════════════════════╝""")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.PORT, reload=True)
