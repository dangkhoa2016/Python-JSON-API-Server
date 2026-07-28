from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import patch

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.requests import Request

from app.database import get_db
from app.middleware.rate_limiter import (
    BLOCK_DURATIONS_SEC,
    _CircuitBreaker,
    _InMemoryStore,
    _mem_store,
    check_redis,
    create_rate_limiter,
    get_client_ip,
)
from app.routes.health import router as health_router
from app.routes.info import router as info_router
from app.routes.resources import router as resources_router


class StatefulFakeRedis:
    def __init__(self, request_count=0, violation_count=0, active_block_seconds=0):
        self._count = request_count
        self._violations = violation_count
        self._block_ttl = active_block_seconds
        self.violation_count = violation_count

    async def eval(
        self, script, num_keys, count_key, block_key, violation_key, max_requests, window_sec
    ):
        if self._block_ttl > 0:
            return [self._count, 0, self._block_ttl, self._block_ttl, 1]

        self._count += 1

        if self._count > max_requests:
            self._violations += 1
            idx = min(self._violations - 1, len(BLOCK_DURATIONS_SEC) - 1)
            block_sec = BLOCK_DURATIONS_SEC[idx]
            self._block_ttl = block_sec
            self.violation_count = self._violations
            return [self._count, 0, block_sec, block_sec, 1]
        else:
            return [self._count, max(0, max_requests - self._count), window_sec, 0, 0]


@pytest.fixture(autouse=True)
def reset_mem_store() -> None:
    _mem_store._data.clear()


class _MockRedisClient:
    connected = False


@pytest_asyncio.fixture
async def rate_limited_app(test_engine: Any, seed_test_data: AsyncSession) -> Any:
    from fastapi import FastAPI

    from app.services.runtime_config import RateLimitConfig

    session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    app = FastAPI(title="test-rl", lifespan=None)
    app.dependency_overrides[get_db] = override_get_db

    mock_redis = _MockRedisClient()
    rl_config = RateLimitConfig(enabled=True, max_requests=100, window_ms=60000)
    RateLimiterMiddleware = create_rate_limiter(mock_redis, rl_config)
    app.add_middleware(RateLimiterMiddleware)

    app.include_router(health_router)
    app.include_router(info_router)
    app.include_router(resources_router)

    yield app
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def rl_client(rate_limited_app: Any) -> AsyncGenerator[httpx.AsyncClient, None]:
    transport = httpx.ASGITransport(app=rate_limited_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


class TestRateLimitHeaders:
    async def test_headers_present(self, rl_client: httpx.AsyncClient) -> None:
        resp = await rl_client.get("/api/users")
        assert resp.status_code == 200
        assert "X-RateLimit-Limit" in resp.headers
        assert "X-RateLimit-Remaining" in resp.headers
        assert "X-RateLimit-Reset" in resp.headers
        assert "X-RateLimit-Store" in resp.headers
        assert resp.headers["X-RateLimit-Store"] == "memory"

    async def test_reset_is_epoch_timestamp(self, rl_client: httpx.AsyncClient) -> None:
        import time

        resp = await rl_client.get("/api/users")
        assert resp.status_code == 200
        reset = int(resp.headers["X-RateLimit-Reset"])
        assert reset >= int(time.time())


class TestExemptRoutes:
    async def test_health_exempt(self, rl_client: httpx.AsyncClient) -> None:
        resp = await rl_client.get("/health")
        assert resp.status_code == 200
        assert "X-RateLimit-Limit" not in resp.headers

    async def test_non_exempt_route_has_headers(self, rl_client: httpx.AsyncClient) -> None:
        resp = await rl_client.get("/api/users")
        assert resp.status_code == 200
        assert "X-RateLimit-Limit" in resp.headers


def test_exempt_routes_only_include_real_endpoints() -> None:
    from app.middleware.rate_limiter import EXEMPT_ROUTES

    assert "/status" not in EXEMPT_ROUTES
    assert "/health" in EXEMPT_ROUTES


class TestGetClientIp:
    @staticmethod
    def _make_request(client_host: str, headers: dict[str, str] | None = None) -> Request:
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "root_path": "",
            "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
            "client": (client_host, 12345),
            "server": ("testserver", 80),
        }
        return Request(scope)

    def test_untrusted_peer_cannot_spoof_x_real_ip(self) -> None:
        request = self._make_request(
            "203.0.113.9",
            {"x-forwarded-for": "198.51.100.77", "x-real-ip": "127.0.0.1"},
        )
        assert get_client_ip(request) == "203.0.113.9"

    def test_private_network_peer_is_untrusted_by_default(self) -> None:
        request = self._make_request(
            "10.0.0.1",
            {"x-forwarded-for": "198.51.100.77"},
        )
        assert get_client_ip(request) == "10.0.0.1"

    def test_trusted_peer_multi_hop(self) -> None:
        request = self._make_request(
            "127.0.0.1",
            {"x-forwarded-for": "203.0.113.9, 127.0.0.1"},
        )
        assert get_client_ip(request) == "203.0.113.9"

    def test_trusted_peer_empty_xff(self) -> None:
        request = self._make_request("127.0.0.1", {})
        assert get_client_ip(request) == "127.0.0.1"

    def test_trusted_peer_malformed_xff(self) -> None:
        request = self._make_request("127.0.0.1", {"x-forwarded-for": "!!!"})
        assert get_client_ip(request) == "127.0.0.1"

    def test_ipv4_mapped_ipv6_normalized(self) -> None:
        request = self._make_request("::ffff:10.0.0.1")
        assert get_client_ip(request) == "10.0.0.1"

    def test_trusted_peer_invalid_x_real_ip_falls_back_to_peer(self) -> None:
        request = self._make_request("127.0.0.1", {"x-real-ip": "not-an-ip"})
        assert get_client_ip(request) == "127.0.0.1"

    def test_trusted_proxies_read_from_settings(self, monkeypatch: Any) -> None:
        from app.middleware import rate_limiter

        monkeypatch.setattr(rate_limiter, "TRUSTED_PROXIES", ["203.0.113.0/24"])
        request = self._make_request(
            "203.0.113.5",
            {"x-forwarded-for": "198.51.100.77, 203.0.113.5"},
        )
        assert get_client_ip(request) == "198.51.100.77"


class TestInMemoryStoreContract:
    async def test_first_request_allowed(self) -> None:
        store = _InMemoryStore()
        result = await store.increment("test", 5, 60000)
        assert result["count"] == 1
        assert result["remaining"] == 4
        assert result["limited"] is False
        assert result["retryAfter"] == 0

    async def test_first_violation_blocks_300s(self) -> None:
        store = _InMemoryStore()
        for _ in range(5):
            await store.increment("test", 5, 60000)
        result = await store.increment("test", 5, 60000)
        assert result["limited"] is True
        assert result["retryAfter"] == 300
        assert result["remaining"] == 0

    async def test_block_does_not_escalate(self, monkeypatch: Any) -> None:
        import time

        fake_now = [1000.0]
        monkeypatch.setattr(time, "time", lambda: fake_now[0])

        store = _InMemoryStore()

        for _ in range(6):
            await store.increment("test", 5, 60000)

        result = await store.increment("test", 5, 60000)
        assert result["limited"] is True
        assert result["retryAfter"] == 300

        result2 = await store.increment("test", 5, 60000)
        assert result2["limited"] is True
        assert result2["count"] == result["count"]
        assert result2["retryAfter"] == 300

    async def test_redis_memory_equivalence(self) -> None:
        limit = 5
        window_ms = 60000
        window_sec = 60

        mem = _InMemoryStore()
        redis = StatefulFakeRedis()
        cb = _CircuitBreaker(failure_threshold=100, reset_timeout_sec=60)

        for _ in range(limit):
            mem_result = await mem.increment("k", limit, window_ms)
            with patch("app.middleware.rate_limiter._circuit_breaker", cb):
                redis_result = await check_redis(redis, "k", limit, window_sec)
            assert mem_result["count"] == redis_result["count"]
            assert mem_result["remaining"] == redis_result["remaining"]
            assert mem_result["limited"] == redis_result["limited"]
            assert mem_result["retryAfter"] == redis_result["retryAfter"]
            assert abs(mem_result["reset"] - redis_result["reset"]) <= 1

        mem_result = await mem.increment("k", limit, window_ms)
        with patch("app.middleware.rate_limiter._circuit_breaker", cb):
            redis_result = await check_redis(redis, "k", limit, window_sec)
        assert mem_result["limited"] is True
        assert redis_result["limited"] is True
        assert mem_result["retryAfter"] == 300
        assert redis_result["retryAfter"] == 300
        assert mem_result["count"] == redis_result["count"]
        assert abs(mem_result["reset"] - redis_result["reset"]) <= 1

        mem_result = await mem.increment("k", limit, window_ms)
        with patch("app.middleware.rate_limiter._circuit_breaker", cb):
            redis_result = await check_redis(redis, "k", limit, window_sec)
        assert mem_result["limited"] is True
        assert redis_result["limited"] is True
        assert mem_result["count"] == redis_result["count"]

    async def test_escalation_across_blocks(self, monkeypatch: Any) -> None:
        import time

        fake_now = [1000.0]
        monkeypatch.setattr(time, "time", lambda: fake_now[0])

        store = _InMemoryStore()

        # First violation block 300s
        for _ in range(6):
            await store.increment("test", 5, 60000)
        result = await store.increment("test", 5, 60000)
        assert result["limited"] is True
        assert result["retryAfter"] == 300

        fake_now[0] += 301

        result = await store.increment("test", 5, 60000)
        assert result["limited"] is False

        for _ in range(5):
            await store.increment("test", 5, 60000)
        result = await store.increment("test", 5, 60000)
        assert result["limited"] is True
        assert result["retryAfter"] == 1200

        fake_now[0] += 1201

        result = await store.increment("test", 5, 60000)
        assert result["limited"] is False

        for _ in range(5):
            await store.increment("test", 5, 60000)
        result = await store.increment("test", 5, 60000)
        assert result["limited"] is True
        assert result["retryAfter"] == 3600
