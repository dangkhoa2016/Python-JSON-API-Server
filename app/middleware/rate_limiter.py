from __future__ import annotations

import asyncio
import ipaddress
import logging
import math
import time
from collections import OrderedDict
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import settings
from app.services.runtime_config import RateLimitConfig

logger = logging.getLogger(__name__)

DEFAULT_WINDOW_MS = 60_000
CLEANUP_INTERVAL_SEC = 300
MAX_MEM_ENTRIES = 10_000
BLOCK_DURATIONS_SEC = [300, 1200, 3600]

RATE_LIMIT_LUA_SCRIPT = """
local countKey = KEYS[1]
local blockKey = KEYS[2]
local violationKey = KEYS[3]
local maxRequests = tonumber(ARGV[1])
local windowSec = tonumber(ARGV[2])
local blockDurations = {300, 1200, 3600}

local blockTTL = redis.call('TTL', blockKey)
if blockTTL > 0 then
  local count = tonumber(redis.call('GET', countKey) or 0)
  return {count, 0, blockTTL, blockTTL, 1}
end

local count = redis.call('INCR', countKey)

if count == 1 then
  redis.call('EXPIRE', countKey, windowSec)
end

if count > maxRequests then
  local violationCount = redis.call('INCR', violationKey)
  if violationCount == 1 then
    redis.call('EXPIRE', violationKey, 14400)  -- 4 hours
  end
  local idx = math.min(violationCount - 1, #blockDurations - 1)
  local blockSec = blockDurations[idx + 1]
  redis.call('SETEX', blockKey, blockSec, 1)
  return {count, 0, blockSec, blockSec, 1}
else
  local ttl = redis.call('TTL', countKey)
  if ttl < 0 then
    ttl = windowSec
  end
  return {count, math.max(0, maxRequests - count), ttl, 0, 0}
end
"""

TRUSTED_PROXIES = list(settings.TRUSTED_PROXIES)

REQUEST_COST = {
    "GET": 1,
    "HEAD": 1,
    "POST": 2,
    "PUT": 2,
    "PATCH": 2,
    "DELETE": 3,
}

EXEMPT_ROUTES = ["/health", "/api/health", "/favicon.ico"]


def window_seconds(window_ms: int) -> int:
    return max(1, math.ceil(window_ms / 1000))


def _cidr_match(ip_str: str, cidr: str) -> bool:
    try:
        network = ipaddress.ip_network(cidr, strict=False)
        addr = ipaddress.ip_address(ip_str)
        return addr in network
    except ValueError:
        return False


def is_trusted_proxy(ip: str) -> bool:
    if not ip or ip == "unknown":
        return False
    for proxy in TRUSTED_PROXIES:
        if "/" in proxy:
            if _cidr_match(ip, proxy):
                return True
        else:
            if ip == proxy:
                return True
    return False


def normalize_ip(ip: str | None) -> str:
    if not ip or ip == "unknown":
        return "unknown"
    if ip.startswith("::ffff:"):
        ip = ip[7:]
    return ip.lower()


def get_client_ip(request: Request) -> str:
    peer = normalize_ip(request.client.host if request.client else None)
    if not peer or peer == "unknown":
        return "unknown"

    if not is_trusted_proxy(peer):
        return peer

    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        ips = []
        for p in xff.split(","):
            normalized = normalize_ip(p.strip())
            if normalized and normalized != "unknown":
                try:
                    ipaddress.ip_address(normalized)
                except ValueError:
                    continue
                ips.append(normalized)
        for ip in reversed(ips):
            if not is_trusted_proxy(ip):
                return ip
        return ips[0] if ips else peer

    real_ip = normalize_ip(request.headers.get("x-real-ip"))
    if real_ip and real_ip != "unknown":
        try:
            ipaddress.ip_address(real_ip)
        except ValueError:
            return peer
        return real_ip

    return peer


def get_request_cost(request: Request) -> int:
    return REQUEST_COST.get(request.method, 1)


class _InMemoryStore:
    def __init__(self, max_entries: int = MAX_MEM_ENTRIES) -> None:
        self._data: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._max_entries = max_entries
        self._last_cleanup = time.monotonic()
        self._lock = asyncio.Lock()

    def get(self, key: str) -> dict[str, Any] | None:
        if key in self._data:
            self._data.move_to_end(key)
            return self._data[key]
        return None

    def set(self, key: str, value: dict[str, Any]) -> None:
        if key in self._data:
            self._data.move_to_end(key)
        self._data[key] = value
        self._ensure_limit()
        self._maybe_cleanup()

    def _ensure_limit(self) -> None:
        while len(self._data) > self._max_entries:
            self._data.popitem(last=False)

    def _maybe_cleanup(self) -> None:
        now = time.monotonic()
        if now - self._last_cleanup < CLEANUP_INTERVAL_SEC:
            return
        self._last_cleanup = now
        now_ms = time.time() * 1000
        expired = [
            k
            for k, v in self._data.items()
            if v.get("windowResetAt", 0) <= now_ms and v.get("blockedUntil", 0) <= now_ms
        ]
        for k in expired:
            del self._data[k]

    async def increment(self, key: str, limit: int, window_ms: int) -> dict[str, Any]:
        async with self._lock:
            now_ms = time.time() * 1000
            entry = self.get(key)

            if not entry:
                entry = {
                    "count": 0,
                    "windowResetAt": now_ms + window_ms,
                    "violationCount": 0,
                    "blockedUntil": 0,
                }

            blocked_until = entry.get("blockedUntil", 0)
            if blocked_until > now_ms:
                remaining_sec = math.ceil((blocked_until - now_ms) / 1000)
                return {
                    "count": entry["count"],
                    "remaining": 0,
                    "reset": math.floor(blocked_until / 1000),
                    "retryAfter": remaining_sec,
                    "limited": True,
                }

            window_reset_at = entry.get("windowResetAt", 0)
            if window_reset_at <= now_ms:
                entry["count"] = 0
                entry["windowResetAt"] = now_ms + window_ms

            entry["count"] = entry.get("count", 0) + 1

            limited = False
            retry_after = 0
            if entry["count"] > limit:
                entry["violationCount"] = entry.get("violationCount", 0) + 1
                idx = min(entry["violationCount"] - 1, len(BLOCK_DURATIONS_SEC) - 1)
                block_sec = BLOCK_DURATIONS_SEC[idx]
                entry["blockedUntil"] = now_ms + block_sec * 1000
                limited = True
                retry_after = math.ceil(block_sec)

            self.set(key, entry)

            reset_epoch = math.floor(entry["windowResetAt"] / 1000)
            if limited:
                reset_epoch = math.floor(entry["blockedUntil"] / 1000)

            return {
                "count": entry["count"],
                "remaining": max(0, limit - entry["count"]),
                "reset": reset_epoch,
                "retryAfter": retry_after,
                "limited": limited,
            }


_mem_store = _InMemoryStore()


class _CircuitBreaker:
    def __init__(self, failure_threshold: int = 3, reset_timeout_sec: float = 30) -> None:
        self.is_open = False
        self.failure_count = 0
        self.last_failure = 0.0
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout_sec

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure = time.monotonic()
        if self.failure_count >= self.failure_threshold:
            self.is_open = True

    def record_success(self) -> None:
        self.failure_count = 0

    def allow(self) -> bool:
        if not self.is_open:
            return True
        if time.monotonic() - self.last_failure > self.reset_timeout:
            self.is_open = False
            self.failure_count = 0
            return True
        return False


_circuit_breaker = _CircuitBreaker()


async def mem_fallback(ip: str, effective_max: int, window_ms: int) -> dict[str, Any]:
    return await _mem_store.increment(ip, effective_max, window_ms)


async def check_redis(
    redis_client: Any, ip: str, effective_max: int, window_sec: int
) -> dict[str, Any]:
    if not _circuit_breaker.allow():
        raise RuntimeError("Circuit breaker open")

    retries = 0
    max_retries = 3
    last_exc: Exception | None = None

    while retries < max_retries:
        try:
            count_key = f"rl:{ip}"
            block_key = f"rl:block:{ip}"
            violation_key = f"rl:violation:{ip}"
            result = await redis_client.eval(
                RATE_LIMIT_LUA_SCRIPT,
                3,
                count_key,
                block_key,
                violation_key,
                effective_max,
                window_sec,
            )
            _circuit_breaker.record_success()
            return {
                "count": result[0],
                "remaining": result[1],
                "reset": int(time.time()) + int(result[2]),
                "retryAfter": result[3],
                "limited": bool(result[4]),
            }
        except Exception as exc:
            retries += 1
            last_exc = exc
            _circuit_breaker.record_failure()
            if retries < max_retries:
                await asyncio.sleep(0.1 * (2**retries))

    raise RuntimeError(f"Max retries exceeded: {last_exc}")


def is_exempt_route(path: str, exempt_routes: list[str] | None = None) -> bool:
    routes = exempt_routes or EXEMPT_ROUTES
    return path in routes


def create_rate_limiter(redis_client: Any, config: RateLimitConfig) -> type[BaseHTTPMiddleware]:
    class RateLimiterMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next: Any) -> Any:
            if not config.enabled:
                return await call_next(request)

            path = request.url.path
            if is_exempt_route(path):
                return await call_next(request)

            ip = get_client_ip(request)
            if not ip or ip == "unknown":
                return await call_next(request)

            cost = get_request_cost(request)
            effective_max = max(1, config.max_requests // cost)
            window_sec = window_seconds(config.window_ms)

            info: dict[str, Any]
            using_redis = False

            try:
                if redis_client and redis_client.connected:
                    info = await check_redis(redis_client, ip, effective_max, window_sec)
                    using_redis = True
                else:
                    info = await mem_fallback(ip, effective_max, config.window_ms)
            except Exception as exc:
                logger.error("Redis error, falling back to memory: %s", exc)
                info = await mem_fallback(ip, effective_max, config.window_ms)

            response: Any
            if info["limited"]:
                logger.warning(
                    "Rate limit exceeded: ip=%s path=%s retryAfter=%s",
                    ip,
                    path,
                    info["retryAfter"],
                )
                retry_after = info["retryAfter"]
                response = JSONResponse(
                    status_code=429,
                    content={
                        "error": "Too Many Requests",
                        "message": (
                            f"Rate limit exceeded. Max {config.max_requests} requests "
                            f"per {window_sec}s window."
                        ),
                        "retryAfter": retry_after,
                    },
                )
                response.headers["Retry-After"] = str(retry_after)
            else:
                response = await call_next(request)

            response.headers["X-RateLimit-Limit"] = str(effective_max)
            response.headers["X-RateLimit-Remaining"] = str(info["remaining"])
            response.headers["X-RateLimit-Reset"] = str(info["reset"])
            response.headers["X-RateLimit-Store"] = "redis" if using_redis else "memory"

            return response

        def update_config(self, updates: dict[str, Any]) -> None:
            config.update(updates)

    RateLimiterMiddleware.config = config  # type: ignore[attr-defined]  # runtime attribute on dynamically created class
    middleware = RateLimiterMiddleware

    return middleware
