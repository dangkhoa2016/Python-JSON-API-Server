from __future__ import annotations

import asyncio
import re
import time
from collections import OrderedDict

from argon2 import PasswordHasher
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Setting

_ph = PasswordHasher()

_auth_cache: OrderedDict[str, tuple[float, bool]] = OrderedDict()
_AUTH_CACHE_TTL_S = 5.0
_AUTH_CACHE_MAX = 1000


def _get_cached_auth(token: str) -> bool | None:
    entry = _auth_cache.get(token)
    if entry is not None:
        ts, valid = entry
        if (time.monotonic() - ts) < _AUTH_CACHE_TTL_S:
            _auth_cache.move_to_end(token)
            return valid
        del _auth_cache[token]
    return None


def _set_cached_auth(token: str, valid: bool) -> None:
    if len(_auth_cache) >= _AUTH_CACHE_MAX:
        expired_keys = [
            k for k, (ts, _) in _auth_cache.items() if (time.monotonic() - ts) >= _AUTH_CACHE_TTL_S
        ]
        for k in expired_keys:
            del _auth_cache[k]
        if len(_auth_cache) >= _AUTH_CACHE_MAX:
            _auth_cache.popitem(last=False)
    _auth_cache[token] = (time.monotonic(), valid)


def reset_auth_cache() -> None:
    _auth_cache.clear()


async def check_admin_auth(request: Request, db: AsyncSession) -> bool:
    if not settings.ADMIN_KEY:
        return False

    auth_header = request.headers.get("authorization", "")
    match = re.match(r"^Bearer\s+(.+)$", auth_header, re.IGNORECASE)
    if not match:
        return False

    token = match.group(1)

    cached = _get_cached_auth(token)
    if cached is not None:
        return cached

    try:
        result = await db.execute(select(Setting).where(Setting.key == "ADMIN_KEY"))
        row = result.scalar_one_or_none()
        if row is None:
            _set_cached_auth(token, False)
            return False

        valid = await asyncio.to_thread(_ph.verify, row.value, token)
        _set_cached_auth(token, valid)
        return valid
    except Exception:
        _set_cached_auth(token, False)
        return False
