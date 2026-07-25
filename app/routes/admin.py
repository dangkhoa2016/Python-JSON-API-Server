import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

from argon2 import PasswordHasher
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import engine, get_db
from app.middleware.auth import check_admin_auth, reset_auth_cache
from app.models import Setting
from app.routes.resources import MODEL_MAP
from app.services.runtime_config import RateLimitConfig
from app.services.runtime_settings import (
    InvalidRuntimeSetting,
    parse_runtime_setting,
    reload_settings_cache,
)
from app.services.seed import apply_seed_payload, fetch_seed_payload

logger = logging.getLogger(__name__)

router = APIRouter()

_ph = PasswordHasher()

SENSITIVE_KEYS = {"REDIS_PASSWORD", "REDIS_URL", "ADMIN_KEY"}

RATE_LIMIT_SETTINGS = {"RATE_LIMIT_ENABLED", "RATE_LIMIT_MAX", "RATE_LIMIT_WINDOW_MS"}
REDIS_SETTINGS = {"REDIS_HOST", "REDIS_PORT", "REDIS_DB", "REDIS_PASSWORD", "REDIS_URL"}

RESET_LOCK_TIMEOUT_S = 30
_reset_lock = asyncio.Lock()


async def _get_redis_client(request: Request) -> Any:
    return getattr(request.app.state, "redis_client", None)


async def _get_rate_limit_config(request: Request) -> RateLimitConfig:
    return getattr(
        request.app.state,
        "rate_limit_config",
        RateLimitConfig(enabled=True, max_requests=100, window_ms=60000),
    )


def _mask_setting(row: Setting) -> dict[str, Any]:
    return {
        "id": row.id,
        "key": row.key,
        "value": "***" if row.key in SENSITIVE_KEYS else row.value,
        "description": row.description,
        "updated_at": row.updated_at,
    }


async def _json_body(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from None
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="JSON body must be an object") from None
    return body


async def _apply_rate_limit_update(key: str, raw_value: str, config: RateLimitConfig) -> None:
    if config is None:
        return
    updates: dict[str, Any] = {}
    if key == "RATE_LIMIT_ENABLED":
        updates["enabled"] = raw_value.lower() != "false"
    elif key == "RATE_LIMIT_MAX":
        try:
            updates["max"] = int(raw_value)
        except ValueError:
            return
    elif key == "RATE_LIMIT_WINDOW_MS":
        try:
            updates["windowMs"] = int(raw_value)
        except ValueError:
            return
    if updates:
        config.update(updates)


async def _apply_redis_update(redis_client: Any, db: AsyncSession) -> None:
    if not redis_client:
        return
    result = await db.execute(
        select(Setting).where(
            Setting.key.in_(["REDIS_URL", "REDIS_HOST", "REDIS_PORT", "REDIS_DB", "REDIS_PASSWORD"])
        )
    )
    rows = result.scalars().all()
    vals = {r.key: r.value for r in rows}

    if vals.get("REDIS_URL"):
        opts: dict[str, Any] = {"url": vals["REDIS_URL"]}
    else:
        opts = {
            "host": vals.get("REDIS_HOST", "127.0.0.1"),
            "port": int(vals.get("REDIS_PORT", "6379")),
            "db": int(vals.get("REDIS_DB", "0")),
            "password": vals.get("REDIS_PASSWORD") or None,
        }
    await redis_client.reconnect(opts)


# ── Routes ──────────────────────────────────────────────────────────────


@router.get("/api/admin/settings")
async def list_settings(
    request: Request,
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> list[dict[str, Any]]:
    if not await check_admin_auth(request, db):
        raise HTTPException(status_code=401, detail="Unauthorized")

    result = await db.execute(select(Setting))
    rows = result.scalars().all()
    return [_mask_setting(r) for r in rows]


@router.patch("/api/admin/settings/{key}")
async def update_setting(
    key: str,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),  # noqa: B008
    redis_client: Any = Depends(_get_redis_client),  # noqa: B008
    rate_limit_config: RateLimitConfig = Depends(_get_rate_limit_config),  # noqa: B008
) -> dict[str, Any]:
    if not await check_admin_auth(request, db):
        raise HTTPException(status_code=401, detail="Unauthorized")

    body = await _json_body(request)
    if "value" not in body:
        raise HTTPException(status_code=400, detail='Missing "value" in request body')

    try:
        raw_value = parse_runtime_setting(key, body["value"])
    except InvalidRuntimeSetting as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e
    val_to_store = await asyncio.to_thread(_ph.hash, raw_value) if key == "ADMIN_KEY" else raw_value
    now = datetime.now(UTC).isoformat()

    result = await db.execute(select(Setting).where(Setting.key == key))
    existing = result.scalar_one_or_none()

    response.status_code = 200 if existing else 201
    if existing:
        existing.value = val_to_store
        existing.updated_at = now
    else:
        db.add(Setting(key=key, value=val_to_store, description="", updated_at=now))

    previous_enabled: bool | None = None
    previous_max: int | None = None
    previous_window_ms: int | None = None
    if key in RATE_LIMIT_SETTINGS:
        previous_enabled = rate_limit_config.enabled
        previous_max = rate_limit_config.max_requests
        previous_window_ms = rate_limit_config.window_ms

    await db.flush()

    try:
        if key in RATE_LIMIT_SETTINGS:
            await _apply_rate_limit_update(key, raw_value, rate_limit_config)
        elif key in REDIS_SETTINGS:
            await _apply_redis_update(redis_client, db)
        elif key == "DEBUG_SQL":
            engine.echo = raw_value.lower() == "true"
    except Exception:
        await db.rollback()
        if previous_enabled is not None:
            rate_limit_config.enabled = previous_enabled
            rate_limit_config.max_requests = previous_max  # type: ignore[assignment]
            rate_limit_config.window_ms = previous_window_ms  # type: ignore[assignment]
        logger.exception("Failed to apply runtime update for %s", key)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from None

    await reload_settings_cache(db)

    result = await db.execute(select(Setting).where(Setting.key == key))
    updated = result.scalar_one()
    payload = _mask_setting(updated)

    await db.commit()

    if key == "ADMIN_KEY":
        reset_auth_cache()

    return payload


@router.post("/api/admin/reset-database")
async def reset_database(
    request: Request,
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> dict[str, str]:
    if not await check_admin_auth(request, db):
        raise HTTPException(status_code=401, detail="Unauthorized")

    body = await _json_body(request)
    if body.get("confirm") is not True:
        raise HTTPException(status_code=400, detail="Reset requires confirm: true in request body")

    try:
        await asyncio.wait_for(_reset_lock.acquire(), timeout=RESET_LOCK_TIMEOUT_S)
    except TimeoutError:
        raise HTTPException(
            status_code=503, detail="Reset timed out — another reset may be in progress"
        ) from None

    try:
        try:
            payload = await fetch_seed_payload(settings.SEED_API_BASE_URL)
        except Exception as exc:
            raise HTTPException(status_code=502, detail="Failed to fetch seed data") from exc

        delete_order = ["photos", "comments", "albums", "posts", "todos", "users"]
        for table_name in delete_order:
            model = MODEL_MAP[table_name]
            await db.execute(delete(model))

        try:
            await db.execute(text("DELETE FROM sqlite_sequence"))
        except Exception:
            pass

        await apply_seed_payload(db, payload, commit=False)
        await db.commit()
    except HTTPException:
        raise
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Database reset failed") from None
    finally:
        _reset_lock.release()

    return {"message": "Database reset and re-seeded successfully"}
