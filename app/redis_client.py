from __future__ import annotations

import errno
import logging
from typing import Any

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

_ERRNO_HINTS: dict[int, str] = {
    errno.ECONNREFUSED: "Is the Redis server running on {host}:{port}?",
    errno.ETIMEDOUT: "Connection timed out - check network or firewall settings.",
    errno.EHOSTUNREACH: "Host is unreachable - check the configured host address.",
    errno.ECONNRESET: "Connection was reset by the peer.",
}


def _root_os_error(exc: BaseException) -> OSError | None:
    """Find the root OSError in an exception chain (cause or context)."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, OSError):
            return current
        current = current.__cause__ or current.__context__
    return None


def _format_redis_error(exc: BaseException, host: str, port: int) -> str:
    os_error = _root_os_error(exc)
    if os_error is not None and os_error.errno is not None:
        name = errno.errorcode.get(os_error.errno, "UNKNOWN")
        text = os_error.strerror or str(exc)
        message = (
            f"Redis connection failed at {host}:{port}: {text} [errno {os_error.errno} / {name}]"
        )
        hint = _ERRNO_HINTS.get(os_error.errno)
        if hint is not None:
            hint = hint.replace("{host}", str(host)).replace("{port}", str(port))
            message = f"{message}. {hint}"
        return message
    return f"Redis connection failed at {host}:{port}: {exc} [{type(exc).__name__}]"


class RedisClient:
    def __init__(self) -> None:
        self._redis: aioredis.Redis | None = None
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected and self._redis is not None

    def _endpoint(self) -> tuple[str, int]:
        if self._redis is None:
            return "127.0.0.1", 6379
        kwargs = self._redis.connection_pool.connection_kwargs
        return str(kwargs.get("host", "127.0.0.1")), int(kwargs.get("port", 6379))

    async def connect(self, opts: dict[str, Any] | None = None) -> None:
        if opts and "url" in opts:
            self._redis = aioredis.from_url(
                opts["url"],
                decode_responses=True,
                socket_connect_timeout=5,
            )
        else:
            o = opts or {}
            self._redis = aioredis.Redis(
                host=o.get("host", "127.0.0.1"),
                port=o.get("port", 6379),
                db=o.get("db", 0),
                password=o.get("password"),
                decode_responses=True,
                socket_connect_timeout=5,
            )
        try:
            await self.ping()
            self._connected = True
            logger.info("Redis connected")
        except Exception as exc:
            self._connected = False
            host, port = self._endpoint()
            logger.warning(_format_redis_error(exc, host, port))

    async def ping(self) -> bool:
        if not self._redis:
            return False
        return await self._redis.ping()

    async def eval(
        self,
        script: str,
        numkeys: int,
        *args: Any,
    ) -> Any:
        if not self._redis:
            raise RuntimeError("Redis not connected")
        return await self._redis.eval(script, numkeys, *args)

    async def reconnect(self, opts: dict[str, Any] | None = None) -> None:
        await self.quit()
        await self.connect(opts)

    async def quit(self) -> None:
        if self._redis:
            try:
                await self._redis.aclose()
            except Exception:
                pass
            self._redis = None
            self._connected = False
            logger.info("Redis disconnected")
