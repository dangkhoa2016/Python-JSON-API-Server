from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.middleware.rate_limiter import (
    CLEANUP_INTERVAL_SEC,
    _cidr_match,
    _CircuitBreaker,
    _InMemoryStore,
    _mem_store,
    check_redis,
    create_rate_limiter,
    get_client_ip,
    get_request_cost,
    is_exempt_route,
    is_trusted_proxy,
    normalize_ip,
    window_seconds,
)
from tests.test_rate_limiter import StatefulFakeRedis


@pytest.fixture(autouse=True)
def reset_mem_store() -> None:
    _mem_store._data.clear()


class TestCidrMatch:
    def test_ip_in_cidr(self) -> None:
        assert _cidr_match("192.168.1.1", "192.168.0.0/16") is True

    def test_ip_not_in_cidr(self) -> None:
        assert _cidr_match("10.0.0.1", "192.168.0.0/16") is False

    def test_invalid_cidr(self) -> None:
        assert _cidr_match("1.2.3.4", "not-a-cidr") is False

    def test_invalid_ip(self) -> None:
        assert _cidr_match("not-an-ip", "192.168.0.0/16") is False

    def test_exact_network_match(self) -> None:
        assert _cidr_match("192.168.0.1", "192.168.0.1/32") is True

    def test_broadcast_address(self) -> None:
        assert _cidr_match("192.168.0.255", "192.168.0.0/24") is True


class TestIsTrustedProxy:
    def test_localhost(self) -> None:
        assert is_trusted_proxy("127.0.0.1") is True

    def test_ipv6_loopback(self) -> None:
        assert is_trusted_proxy("::1") is True

    def test_private_ranges_untrusted_by_default(self) -> None:
        assert is_trusted_proxy("192.168.1.1") is False
        assert is_trusted_proxy("10.0.0.1") is False
        assert is_trusted_proxy("172.16.0.1") is False

    def test_empty_string(self) -> None:
        assert is_trusted_proxy("") is False

    def test_unknown(self) -> None:
        assert is_trusted_proxy("unknown") is False

    def test_public_ip(self) -> None:
        assert is_trusted_proxy("8.8.8.8") is False


class TestNormalizeIp:
    def test_none(self) -> None:
        assert normalize_ip(None) == "unknown"

    def test_unknown(self) -> None:
        assert normalize_ip("unknown") == "unknown"

    def test_ipv4_mapped(self) -> None:
        assert normalize_ip("::ffff:192.168.1.1") == "192.168.1.1"

    def test_lowercase(self) -> None:
        assert normalize_ip("ABC") == "abc"

    def test_normal_ip(self) -> None:
        assert normalize_ip("1.2.3.4") == "1.2.3.4"

    def test_empty_string(self) -> None:
        assert normalize_ip("") == "unknown"


class TestGetClientIp:
    def test_xff_with_trusted_remote(self) -> None:
        req = MagicMock()
        req.headers = {"x-forwarded-for": "1.2.3.4, 5.6.7.8"}
        req.client.host = "127.0.0.1"
        assert get_client_ip(req) == "5.6.7.8"

    def test_xreal_ip_fallback(self) -> None:
        req = MagicMock()
        req.headers = {"x-real-ip": "9.8.7.6", "x-forwarded-for": ""}
        req.client.host = "127.0.0.1"
        assert get_client_ip(req) == "9.8.7.6"

    def test_client_host_untrusted(self) -> None:
        req = MagicMock()
        req.headers = {}
        req.client.host = "8.8.8.8"
        assert get_client_ip(req) == "8.8.8.8"

    def test_no_client(self) -> None:
        req = MagicMock()
        req.headers = {}
        req.client = None
        assert get_client_ip(req) == "unknown"

    def test_xff_single_ip(self) -> None:
        req = MagicMock()
        req.headers = {"x-forwarded-for": "10.0.0.1"}
        req.client.host = "127.0.0.1"
        assert get_client_ip(req) == "10.0.0.1"


class TestGetRequestCost:
    def test_get(self) -> None:
        req = MagicMock()
        req.method = "GET"
        assert get_request_cost(req) == 1

    def test_post(self) -> None:
        req = MagicMock()
        req.method = "POST"
        assert get_request_cost(req) == 2

    def test_delete(self) -> None:
        req = MagicMock()
        req.method = "DELETE"
        assert get_request_cost(req) == 3

    def test_unknown_method(self) -> None:
        req = MagicMock()
        req.method = "OPTIONS"
        assert get_request_cost(req) == 1


class TestInMemoryStore:
    def test_get_existing(self) -> None:
        store = _InMemoryStore(max_entries=10)
        now_ms = time.time() * 1000
        store.set("k1", {"val": 1, "windowResetAt": now_ms + 60000, "blockedUntil": 0})
        result = store.get("k1")
        assert result is not None
        assert result["val"] == 1

    def test_get_missing(self) -> None:
        store = _InMemoryStore(max_entries=10)
        assert store.get("missing") is None

    def test_set_and_overwrite(self) -> None:
        store = _InMemoryStore(max_entries=10)
        now_ms = time.time() * 1000
        store.set("k", {"a": 1, "windowResetAt": now_ms + 60000, "blockedUntil": 0})
        store.set("k", {"a": 2, "windowResetAt": now_ms + 60000, "blockedUntil": 0})
        assert store.get("k")["a"] == 2

    def test_ensure_limit_evicts_oldest(self) -> None:
        store = _InMemoryStore(max_entries=2)
        now_ms = time.time() * 1000
        store.set("a", {"v": 1, "windowResetAt": now_ms + 60000, "blockedUntil": 0})
        store.set("b", {"v": 2, "windowResetAt": now_ms + 60000, "blockedUntil": 0})
        store.set("c", {"v": 3, "windowResetAt": now_ms + 60000, "blockedUntil": 0})
        assert store.get("a") is None
        assert store.get("c") is not None

    def test_maybe_cleanup_removes_expired(self) -> None:
        store = _InMemoryStore(max_entries=10)
        store._last_cleanup = 0
        store.set("expired", {"v": 1, "windowResetAt": 1, "blockedUntil": 0})
        with patch(
            "app.middleware.rate_limiter.time.monotonic", return_value=CLEANUP_INTERVAL_SEC + 100
        ):
            store._maybe_cleanup()
        assert store.get("expired") is None

    def test_maybe_cleanup_keeps_valid(self) -> None:
        store = _InMemoryStore(max_entries=10)
        store._last_cleanup = 0
        future = (time.time() + 1000) * 1000
        store.set("alive", {"v": 1, "windowResetAt": future, "blockedUntil": 0})
        store._maybe_cleanup()
        assert store.get("alive") is not None


class TestCircuitBreaker:
    def test_initial_state_allows(self) -> None:
        cb = _CircuitBreaker(failure_threshold=2, reset_timeout_sec=1)
        assert cb.allow() is True

    def test_opens_after_threshold(self) -> None:
        cb = _CircuitBreaker(failure_threshold=2, reset_timeout_sec=60)
        cb.record_failure()
        assert cb.is_open is False
        cb.record_failure()
        assert cb.is_open is True
        assert cb.allow() is False

    def test_success_resets_count(self) -> None:
        cb = _CircuitBreaker(failure_threshold=3, reset_timeout_sec=60)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.failure_count == 0
        assert cb.allow() is True

    def test_timeout_resets_circuit(self) -> None:
        cb = _CircuitBreaker(failure_threshold=1, reset_timeout_sec=0)
        cb.record_failure()
        assert cb.is_open is True
        assert cb.allow() is True
        assert cb.is_open is False
        assert cb.failure_count == 0


class TestMemFallback:
    async def test_first_call_increments(self) -> None:
        store = _InMemoryStore()
        result = await store.increment("1.2.3.4", limit=10, window_ms=60000)
        assert result["count"] == 1
        assert result["remaining"] == 9
        assert result["limited"] is False

    async def test_rate_limited(self) -> None:
        store = _InMemoryStore()
        now_ms = time.time() * 1000
        store.set(
            "1.2.3.4",
            {
                "count": 10,
                "windowResetAt": now_ms + 60000,
                "violationCount": 0,
                "blockedUntil": 0,
            },
        )
        result = await store.increment("1.2.3.4", limit=10, window_ms=60000)
        assert result["count"] == 11
        assert result["limited"] is True
        assert result["retryAfter"] > 0

    async def test_window_expired_resets(self) -> None:
        store = _InMemoryStore()
        store.set(
            "1.2.3.4",
            {"count": 5, "windowResetAt": 1, "violationCount": 2, "blockedUntil": 0},
        )
        result = await store.increment("1.2.3.4", limit=10, window_ms=60000)
        assert result["count"] == 1
        assert result["limited"] is False

    async def test_previous_violations_preserved(self) -> None:
        store = _InMemoryStore()
        now_ms = time.time() * 1000
        store.set(
            "1.2.3.4",
            {
                "count": 10,
                "windowResetAt": now_ms + 60000,
                "violationCount": 2,
                "blockedUntil": 0,
            },
        )
        result = await store.increment("1.2.3.4", limit=10, window_ms=60000)
        assert result["limited"] is True
        assert result["retryAfter"] > 0


class TestCheckRedis:
    @pytest.mark.asyncio
    async def test_success(self) -> None:
        cb = _CircuitBreaker(failure_threshold=3, reset_timeout_sec=60)
        with patch("app.middleware.rate_limiter._circuit_breaker", cb):
            redis = AsyncMock()
            redis.eval = AsyncMock(return_value=[5, 5, 55, 0, 0])
            result = await check_redis(redis, "1.2.3.4", 10, 60)
            assert result["count"] == 5
            assert result["remaining"] == 5
            assert result["limited"] is False
            assert abs(result["reset"] - (int(time.time()) + 55)) <= 1

    @pytest.mark.asyncio
    async def test_circuit_breaker_open(self) -> None:
        cb = _CircuitBreaker(failure_threshold=1, reset_timeout_sec=60)
        cb.record_failure()
        with patch("app.middleware.rate_limiter._circuit_breaker", cb):
            redis = AsyncMock()
            with pytest.raises(RuntimeError, match="Circuit breaker open"):
                await check_redis(redis, "1.2.3.4", 10, 60)

    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self) -> None:
        cb = _CircuitBreaker(failure_threshold=100, reset_timeout_sec=60)
        with patch("app.middleware.rate_limiter._circuit_breaker", cb):
            redis = AsyncMock()
            redis.eval = AsyncMock(side_effect=Exception("redis error"))
            with pytest.raises(RuntimeError, match="Max retries exceeded"):
                await check_redis(redis, "1.2.3.4", 10, 60)
            assert cb.failure_count == 3

    @pytest.mark.asyncio
    async def test_success_after_retry(self) -> None:
        cb = _CircuitBreaker(failure_threshold=100, reset_timeout_sec=60)
        with patch("app.middleware.rate_limiter._circuit_breaker", cb):
            redis = AsyncMock()
            redis.eval = AsyncMock(side_effect=[Exception("err"), [3, 7, 57, 0, 0]])
            result = await check_redis(redis, "1.2.3.4", 10, 60)
            assert result["count"] == 3


class TestIsExemptRoute:
    def test_health_exempt(self) -> None:
        assert is_exempt_route("/health") is True

    def test_non_exempt(self) -> None:
        assert is_exempt_route("/api/users") is False

    def test_custom_list(self) -> None:
        assert is_exempt_route("/custom", ["/custom", "/special"]) is True

    def test_fallback_to_default(self) -> None:
        assert is_exempt_route("/health") is True
        assert is_exempt_route("/api/users") is False


class TestCreateRateLimiter:
    def _make_config(self, enabled: bool = True, max_requests: int = 100, window_ms: int = 60000):
        from app.services.runtime_config import RateLimitConfig

        return RateLimitConfig(enabled=enabled, max_requests=max_requests, window_ms=window_ms)

    def test_creates_middleware_class(self) -> None:
        mock_redis = MagicMock()
        mock_redis.connected = False
        config = self._make_config()
        result = create_rate_limiter(mock_redis, config)
        assert result is not None
        assert hasattr(result, "dispatch")

    @pytest.mark.asyncio
    async def test_disabled_passthrough(self) -> None:
        mock_redis = MagicMock()
        mock_redis.connected = False
        config = self._make_config(enabled=False)
        MW = create_rate_limiter(mock_redis, config)
        mw = MW(app=MagicMock())
        req = MagicMock()
        req.url.path = "/api/users"
        req.method = "GET"
        req.headers = {}
        req.client.host = "1.2.3.4"
        call_next = AsyncMock(return_value=MagicMock(status_code=200))
        resp = await mw.dispatch(req, call_next)
        assert resp.status_code == 200
        call_next.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_exempt_route_passthrough(self) -> None:
        mock_redis = MagicMock()
        mock_redis.connected = False
        config = self._make_config()
        MW = create_rate_limiter(mock_redis, config)
        mw = MW(app=MagicMock())
        req = MagicMock()
        req.url.path = "/health"
        req.method = "GET"
        req.headers = {}
        req.client.host = "127.0.0.1"
        call_next = AsyncMock(return_value=MagicMock(status_code=200))
        resp = await mw.dispatch(req, call_next)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_unknown_ip_passthrough(self) -> None:
        mock_redis = MagicMock()
        mock_redis.connected = False
        config = self._make_config()
        MW = create_rate_limiter(mock_redis, config)
        mw = MW(app=MagicMock())
        req = MagicMock()
        req.url.path = "/api/users"
        req.method = "GET"
        req.headers = {}
        req.client = None
        call_next = AsyncMock(return_value=MagicMock(status_code=200))
        resp = await mw.dispatch(req, call_next)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_normal_response_has_headers(self) -> None:
        mock_redis = MagicMock()
        mock_redis.connected = False
        config = self._make_config()
        MW = create_rate_limiter(mock_redis, config)
        mw = MW(app=MagicMock())
        req = MagicMock()
        req.url.path = "/api/users"
        req.method = "GET"
        req.headers = {}
        req.client.host = "8.8.8.8"
        inner_resp = MagicMock(status_code=200, headers={})
        call_next = AsyncMock(return_value=inner_resp)
        resp = await mw.dispatch(req, call_next)
        assert "X-RateLimit-Limit" in resp.headers
        assert "X-RateLimit-Remaining" in resp.headers

    @pytest.mark.asyncio
    async def test_rate_limited_response_429(self) -> None:
        mock_redis = MagicMock()
        mock_redis.connected = False
        config = self._make_config(max_requests=1)
        MW = create_rate_limiter(mock_redis, config)
        mw = MW(app=MagicMock())
        req = MagicMock()
        req.url.path = "/api/users"
        req.method = "POST"
        req.headers = {}
        req.client.host = "8.8.8.8"
        inner_resp = MagicMock(status_code=200, headers={})
        call_next = AsyncMock(return_value=inner_resp)
        await mw.dispatch(req, call_next)
        resp = await mw.dispatch(req, call_next)
        assert resp.status_code == 429

    @pytest.mark.asyncio
    async def test_redis_error_falls_back_to_memory(self) -> None:
        mock_redis = MagicMock()
        mock_redis.connected = True
        mock_redis.eval = AsyncMock(side_effect=Exception("redis down"))
        config = self._make_config()
        fresh_cb = _CircuitBreaker(failure_threshold=100, reset_timeout_sec=60)
        with patch("app.middleware.rate_limiter._circuit_breaker", fresh_cb):
            MW = create_rate_limiter(mock_redis, config)
            mw = MW(app=MagicMock())
            req = MagicMock()
            req.url.path = "/api/users"
            req.method = "GET"
            req.headers = {}
            req.client.host = "9.9.9.9"
            inner_resp = MagicMock(status_code=200, headers={})
            call_next = AsyncMock(return_value=inner_resp)
            resp = await mw.dispatch(req, call_next)
            assert resp.status_code == 200
            assert resp.headers.get("X-RateLimit-Store") == "memory"

    @pytest.mark.asyncio
    async def test_redis_success_uses_redis_store(self) -> None:
        mock_redis = MagicMock()
        mock_redis.connected = True
        mock_redis.eval = AsyncMock(return_value=[1, 99, 59, 0, 0])
        config = self._make_config()
        fresh_cb = _CircuitBreaker(failure_threshold=100, reset_timeout_sec=60)
        with patch("app.middleware.rate_limiter._circuit_breaker", fresh_cb):
            MW = create_rate_limiter(mock_redis, config)
            mw = MW(app=MagicMock())
            req = MagicMock()
            req.url.path = "/api/users"
            req.method = "GET"
            req.headers = {}
            req.client.host = "8.8.8.8"
            inner_resp = MagicMock(status_code=200, headers={})
            call_next = AsyncMock(return_value=inner_resp)
            resp = await mw.dispatch(req, call_next)
            assert resp.headers.get("X-RateLimit-Store") == "redis"

    @pytest.mark.asyncio
    async def test_update_config_on_middleware_instance(self) -> None:
        mock_redis = MagicMock()
        mock_redis.connected = False
        config = self._make_config()
        MW = create_rate_limiter(mock_redis, config)
        mw = MW(app=MagicMock())
        mw.update_config({"max": 200})
        assert config.max_requests == 200


async def test_shared_config_update_changes_limit_without_rebuild():
    from app.services.runtime_config import RateLimitConfig

    config = RateLimitConfig(enabled=True, max_requests=10, window_ms=60_000)
    MW = create_rate_limiter(redis_client=None, config=config)
    config.update({"max": 1})
    assert MW.config.max_requests == 1


def test_subsecond_window_uses_one_second():
    assert window_seconds(1) == 1
    assert window_seconds(999) == 1
    assert window_seconds(1_001) == 2


async def test_concurrent_memory_requests_have_unique_counts():
    store = _InMemoryStore()
    results = await asyncio.gather(
        *(store.increment("127.0.0.1", limit=100, window_ms=60_000) for _ in range(50))
    )
    assert sorted(item["count"] for item in results) == list(range(1, 51))


async def test_blocked_redis_request_does_not_increment_violation_again():
    redis = StatefulFakeRedis(
        request_count=101,
        violation_count=1,
        active_block_seconds=300,
    )
    first = await check_redis(redis, "127.0.0.1", 100, 60)
    second = await check_redis(redis, "127.0.0.1", 100, 60)
    assert first["limited"] is True
    assert second["limited"] is True
    assert first["retryAfter"] == second["retryAfter"] == 300
    assert redis.violation_count == 1
