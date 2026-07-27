from __future__ import annotations

import errno as errno_module
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import redis.exceptions

from app.redis_client import RedisClient, _format_redis_error, _root_os_error


class TestRedisClientInit:
    def test_initial_state(self) -> None:
        client = RedisClient()
        assert client.connected is False
        assert client._redis is None

    def test_endpoint_defaults_when_not_connected(self) -> None:
        client = RedisClient()
        assert client._endpoint() == ("127.0.0.1", 6379)


class TestRedisClientConnectedProperty:
    def test_not_connected_when_no_redis(self) -> None:
        client = RedisClient()
        client._connected = True
        assert client.connected is False

    def test_not_connected_when_redis_none(self) -> None:
        client = RedisClient()
        client._connected = False
        assert client.connected is False

    def test_connected_when_both_set(self) -> None:
        client = RedisClient()
        client._redis = MagicMock()
        client._connected = True
        assert client.connected is True


class TestRedisClientPing:
    async def test_ping_when_not_connected(self) -> None:
        client = RedisClient()
        result = await client.ping()
        assert result is False


class TestRedisClientEval:
    async def test_eval_when_not_connected(self) -> None:
        client = RedisClient()
        with pytest.raises(RuntimeError, match="Redis not connected"):
            await client.eval("return 1", 0)

    async def test_eval_when_connected(self) -> None:
        client = RedisClient()
        mock_redis = AsyncMock()
        mock_redis.eval = AsyncMock(return_value=[1, 99, 59, 0, 0])
        client._redis = mock_redis
        client._connected = True
        result = await client.eval("return 1", 0)
        assert result == [1, 99, 59, 0, 0]
        mock_redis.eval.assert_called_once_with("return 1", 0)


class TestRedisClientQuit:
    async def test_quit_when_not_connected(self) -> None:
        client = RedisClient()
        await client.quit()
        assert client._redis is None
        assert client._connected is False

    async def test_quit_when_connected(self) -> None:
        client = RedisClient()
        mock_redis = AsyncMock()
        client._redis = mock_redis
        client._connected = True
        await client.quit()
        mock_redis.aclose.assert_called_once()
        assert client._redis is None
        assert client._connected is False

    async def test_quit_aclose_raises(self) -> None:
        client = RedisClient()
        mock_redis = AsyncMock()
        mock_redis.aclose.side_effect = Exception("close error")
        client._redis = mock_redis
        client._connected = True
        await client.quit()
        assert client._redis is None
        assert client._connected is False


class TestRedisClientConnect:
    @patch("app.redis_client.aioredis")
    async def test_connect_with_url(self, mock_aioredis: MagicMock) -> None:
        mock_redis = AsyncMock()
        mock_redis.ping.return_value = True
        mock_aioredis.from_url.return_value = mock_redis

        client = RedisClient()
        await client.connect({"url": "redis://localhost:6379"})

        mock_aioredis.from_url.assert_called_once_with(
            "redis://localhost:6379",
            decode_responses=True,
            socket_connect_timeout=5,
        )
        assert client.connected is True

    @patch("app.redis_client.aioredis")
    async def test_connect_with_host_port(self, mock_aioredis: MagicMock) -> None:
        mock_redis = AsyncMock()
        mock_redis.ping.return_value = True
        mock_aioredis.Redis.return_value = mock_redis

        client = RedisClient()
        await client.connect({"host": "10.0.0.1", "port": 6380, "db": 1, "password": "secret"})

        mock_aioredis.Redis.assert_called_once_with(
            host="10.0.0.1",
            port=6380,
            db=1,
            password="secret",
            decode_responses=True,
            socket_connect_timeout=5,
        )
        assert client.connected is True

    @patch("app.redis_client.aioredis")
    async def test_connect_ping_fails(self, mock_aioredis: MagicMock) -> None:
        mock_redis = AsyncMock()
        mock_redis.ping.side_effect = Exception("connection refused")
        mock_redis.connection_pool.connection_kwargs = {"host": "127.0.0.1", "port": 6379}
        mock_aioredis.from_url.return_value = mock_redis

        client = RedisClient()
        await client.connect({"url": "redis://localhost:6379"})

        assert client.connected is False

    @patch("app.redis_client.aioredis")
    async def test_connect_ping_fails_logs_friendly_message(
        self, mock_aioredis: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        mock_redis = AsyncMock()
        with pytest.raises(redis.exceptions.ConnectionError) as excinfo:
            _wrapped_connection_error(111, "Connection refused")
        mock_redis.ping.side_effect = excinfo.value
        mock_redis.connection_pool.connection_kwargs = {"host": "127.0.0.1", "port": 6379}
        mock_aioredis.from_url.return_value = mock_redis

        client = RedisClient()
        with caplog.at_level(logging.WARNING, logger="app.redis_client"):
            await client.connect({"url": "redis://127.0.0.1:6379"})

        assert client.connected is False
        assert "Redis connection failed at 127.0.0.1:6379" in caplog.text
        assert "[errno 111 / ECONNREFUSED]" in caplog.text
        assert "Is the Redis server running on 127.0.0.1:6379?" in caplog.text

    @patch("app.redis_client.aioredis")
    async def test_connect_ping_fails_logs_generic_fallback(
        self, mock_aioredis: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        mock_redis = AsyncMock()
        mock_redis.ping.side_effect = ValueError("invalid config")
        mock_redis.connection_pool.connection_kwargs = {"host": "10.0.0.1", "port": 6380}
        mock_aioredis.Redis.return_value = mock_redis

        client = RedisClient()
        with caplog.at_level(logging.WARNING, logger="app.redis_client"):
            await client.connect({"host": "10.0.0.1", "port": 6380})

        assert client.connected is False
        assert "Redis connection failed at 10.0.0.1:6380" in caplog.text
        assert "invalid config" in caplog.text
        assert "[ValueError]" in caplog.text

    @patch("app.redis_client.aioredis")
    async def test_connect_with_defaults(self, mock_aioredis: MagicMock) -> None:
        mock_redis = AsyncMock()
        mock_redis.ping.return_value = True
        mock_aioredis.Redis.return_value = mock_redis

        client = RedisClient()
        await client.connect({})

        mock_aioredis.Redis.assert_called_once_with(
            host="127.0.0.1",
            port=6379,
            db=0,
            password=None,
            decode_responses=True,
            socket_connect_timeout=5,
        )

    @patch("app.redis_client.aioredis")
    async def test_connect_with_none_opts(self, mock_aioredis: MagicMock) -> None:
        mock_redis = AsyncMock()
        mock_redis.ping.return_value = True
        mock_aioredis.Redis.return_value = mock_redis

        client = RedisClient()
        await client.connect(None)

        mock_aioredis.Redis.assert_called_once()


class TestRedisClientReconnect:
    @patch("app.redis_client.aioredis")
    async def test_reconnect(self, mock_aioredis: MagicMock) -> None:
        mock_redis_old = AsyncMock()
        mock_redis_new = AsyncMock()
        mock_redis_new.ping.return_value = True
        mock_aioredis.from_url.return_value = mock_redis_new

        client = RedisClient()
        client._redis = mock_redis_old
        client._connected = True

        await client.reconnect({"url": "redis://localhost:6379"})

        mock_redis_old.aclose.assert_called_once()
        assert client.connected is True


def _wrapped_connection_error(
    errno_code: int,
    strerror: str,
    host: str = "127.0.0.1",
    port: int = 6379,
) -> redis.exceptions.ConnectionError:
    """Mimic redis-py: raise the OSError, then raise ConnectionError from it."""
    try:
        raise OSError(errno_code, strerror)
    except OSError as e:
        raise redis.exceptions.ConnectionError(
            f"Error {e.errno} connecting to {host}:{port}. {e.strerror}."
        ) from e


class TestRedisErrorFormatting:
    def test_root_os_error_finds_cause(self) -> None:
        with pytest.raises(redis.exceptions.ConnectionError) as excinfo:
            _wrapped_connection_error(111, "Connection refused")
        root = _root_os_error(excinfo.value)
        assert isinstance(root, OSError)
        assert root.errno == 111

    def test_root_os_error_none_for_plain_exception(self) -> None:
        assert _root_os_error(ValueError("bad config")) is None

    def test_os_error_refused_message(self) -> None:
        exc = ConnectionRefusedError(111, "Connection refused")
        message = _format_redis_error(exc, "127.0.0.1", 6379)
        assert "Redis connection failed at 127.0.0.1:6379" in message
        assert "connection refused" in message.lower()
        assert "111" in message
        assert "ECONNREFUSED" in message
        assert "Is the Redis server running on 127.0.0.1:6379?" in message

    def test_wrapped_redis_connection_error_message(self) -> None:
        with pytest.raises(redis.exceptions.ConnectionError) as excinfo:
            _wrapped_connection_error(111, "Connection refused")
        message = _format_redis_error(excinfo.value, "127.0.0.1", 6379)
        assert "Redis connection failed at 127.0.0.1:6379" in message
        assert "[errno 111 / ECONNREFUSED]" in message

    def test_os_error_timeout_hint(self) -> None:
        exc = OSError(errno_module.ETIMEDOUT, "Connection timed out")
        message = _format_redis_error(exc, "10.0.0.1", 6380)
        assert "Redis connection failed at 10.0.0.1:6380" in message
        assert "[errno 110 / ETIMEDOUT]" in message
        assert "check network or firewall" in message

    def test_generic_exception_fallback(self) -> None:
        exc = ValueError("bad config")
        message = _format_redis_error(exc, "10.0.0.1", 6380)
        assert "Redis connection failed at 10.0.0.1:6380" in message
        assert "bad config" in message
        assert "[ValueError]" in message

    def test_os_error_without_errno_fallback(self) -> None:
        exc = OSError("some socket error")
        assert exc.errno is None
        message = _format_redis_error(exc, "127.0.0.1", 6379)
        assert "[OSError]" in message
