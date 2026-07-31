from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.main import (
    app,
    print_banner,
)
from app.services.runtime_settings import RuntimeSettings


class TestPrintBanner:
    def test_prints_banner(self, capsys: pytest.CaptureFixture[str]) -> None:
        print_banner()
        captured = capsys.readouterr()
        assert "python-json-api-server" in captured.out
        assert "v1.0.0" in captured.out


class TestAppMetadata:
    def test_app_is_fastapi(self) -> None:
        assert isinstance(app, FastAPI)

    def test_app_title(self) -> None:
        assert app.title == "python-json-api-server"

    def test_app_version(self) -> None:
        assert app.version == "1.0.0"


class TestFreshStartup:
    async def test_lifespan_starts_with_fresh_default_settings(
        self, fresh_database: Any, test_app: Any
    ) -> None:
        from app.main import lifespan

        async with lifespan(test_app):
            config = test_app.state.rate_limit_config
            assert config.enabled is True
            assert config.max_requests == 100
            assert config.window_ms == 60000


class TestPoweredByHeaderRemoved:
    async def test_does_not_add_header(self) -> None:
        test_app = FastAPI()

        @test_app.get("/test")
        async def test_route() -> dict:
            return {"ok": True}

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/test")
            assert resp.status_code == 200
            assert "x-powered-by" not in resp.headers


class TestLifespan:
    @patch("app.main.load_runtime_settings")
    @patch("app.main.print_banner")
    @patch("app.main.seed_settings", new_callable=AsyncMock)
    @patch("app.main.redis_client")
    @patch("app.main.async_session")
    @patch("app.main.engine")
    @patch("app.main.init_db", new_callable=AsyncMock)
    async def test_lifespan_calls_init_db(
        self,
        mock_init_db: AsyncMock,
        mock_engine: MagicMock,
        mock_async_session: MagicMock,
        mock_redis: MagicMock,
        mock_seed_settings: AsyncMock,
        mock_banner: MagicMock,
        mock_load: MagicMock,
    ) -> None:
        from app.main import lifespan

        mock_conn = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_engine.begin.return_value = mock_cm

        mock_db = AsyncMock()
        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_cm.__aexit__ = AsyncMock(return_value=False)
        mock_async_session.return_value = mock_session_cm

        mock_redis.connected = False
        mock_redis.quit = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_load.return_value = RuntimeSettings(rate_limit={}, redis={})

        test_app = FastAPI()
        async with lifespan(test_app):
            mock_init_db.assert_called_once()
            mock_seed_settings.assert_called_once_with(mock_db)

        mock_redis.quit.assert_called_once()

    @patch("app.main.load_runtime_settings")
    @patch("app.main.print_banner")
    @patch("app.main.seed_settings", new_callable=AsyncMock)
    @patch("app.main.redis_client")
    @patch("app.main.async_session")
    @patch("app.main.engine")
    @patch("app.main.init_db", new_callable=AsyncMock)
    async def test_lifespan_applies_debug_sql_to_engine_echo(
        self,
        mock_init_db: AsyncMock,
        mock_engine: MagicMock,
        mock_async_session: MagicMock,
        mock_redis: MagicMock,
        mock_seed_settings: AsyncMock,
        mock_banner: MagicMock,
        mock_load: MagicMock,
    ) -> None:
        from app.main import lifespan

        mock_conn = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_engine.begin.return_value = mock_cm

        mock_db = AsyncMock()
        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_cm.__aexit__ = AsyncMock(return_value=False)
        mock_async_session.return_value = mock_session_cm

        mock_redis.connected = False
        mock_redis.quit = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_load.return_value = RuntimeSettings(rate_limit={}, redis={}, debug_sql=True)

        test_app = FastAPI()
        async with lifespan(test_app):
            assert mock_engine.echo is True

    @patch("app.main.load_runtime_settings")
    @patch("app.main.print_banner")
    @patch("app.main.seed_settings", new_callable=AsyncMock)
    @patch("app.main.redis_client")
    @patch("app.main.async_session")
    @patch("app.main.engine")
    @patch("app.main.init_db", new_callable=AsyncMock)
    async def test_lifespan_sets_app_state(
        self,
        mock_init_db: AsyncMock,
        mock_engine: MagicMock,
        mock_async_session: MagicMock,
        mock_redis: MagicMock,
        mock_seed_settings: AsyncMock,
        mock_banner: MagicMock,
        mock_load: MagicMock,
    ) -> None:
        from app.main import lifespan

        mock_conn = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_engine.begin.return_value = mock_cm

        mock_db = AsyncMock()
        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_cm.__aexit__ = AsyncMock(return_value=False)
        mock_async_session.return_value = mock_session_cm

        mock_redis.connected = False
        mock_redis.quit = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_load.return_value = RuntimeSettings(rate_limit={}, redis={})

        test_app = FastAPI()
        async with lifespan(test_app):
            assert test_app.state.redis_client is mock_redis
            assert hasattr(test_app.state, "rate_limit_config")

    @patch("app.main.load_runtime_settings")
    @patch("app.main.print_banner")
    @patch("app.main.seed_settings", new_callable=AsyncMock)
    @patch("app.main.redis_client")
    @patch("app.main.async_session")
    @patch("app.main.engine")
    @patch("app.main.init_db", new_callable=AsyncMock)
    async def test_lifespan_redis_connected(
        self,
        mock_init_db: AsyncMock,
        mock_engine: MagicMock,
        mock_async_session: MagicMock,
        mock_redis: MagicMock,
        mock_seed_settings: AsyncMock,
        mock_banner: MagicMock,
        mock_load: MagicMock,
    ) -> None:
        from app.main import lifespan

        mock_conn = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_engine.begin.return_value = mock_cm

        mock_db = AsyncMock()
        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_cm.__aexit__ = AsyncMock(return_value=False)
        mock_async_session.return_value = mock_session_cm

        mock_redis.connected = True
        mock_redis.quit = AsyncMock()
        mock_redis.connect = AsyncMock()
        mock_load.return_value = RuntimeSettings(rate_limit={}, redis={})

        test_app = FastAPI()
        async with lifespan(test_app):
            mock_redis.connect.assert_called_once()

        mock_redis.quit.assert_called_once()

    @patch("app.main.load_runtime_settings")
    @patch("app.main.print_banner")
    @patch("app.main.seed_settings", new_callable=AsyncMock)
    @patch("app.main.redis_client")
    @patch("app.main.async_session")
    @patch("app.main.engine")
    @patch("app.main.init_db", new_callable=AsyncMock)
    async def test_lifespan_quit_exception_swallows(
        self,
        mock_init_db: AsyncMock,
        mock_engine: MagicMock,
        mock_async_session: MagicMock,
        mock_redis: MagicMock,
        mock_seed_settings: AsyncMock,
        mock_banner: MagicMock,
        mock_load: MagicMock,
    ) -> None:
        from app.main import lifespan

        mock_conn = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_engine.begin.return_value = mock_cm

        mock_db = AsyncMock()
        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_cm.__aexit__ = AsyncMock(return_value=False)
        mock_async_session.return_value = mock_session_cm

        mock_redis.connected = False
        mock_redis.quit = AsyncMock(side_effect=Exception("quit failed"))
        mock_redis.connect = AsyncMock()
        mock_load.return_value = RuntimeSettings(rate_limit={}, redis={})

        test_app = FastAPI()
        async with lifespan(test_app):
            pass

        mock_redis.quit.assert_called_once()

    def test_main_block(self) -> None:
        import runpy

        with patch("uvicorn.run") as mock_run:
            runpy.run_path("app/main.py", run_name="__main__")
            mock_run.assert_called_once()


class TestPersistedSettings:
    @patch("app.main.load_runtime_settings")
    @patch("app.main.print_banner")
    @patch("app.main.seed_settings", new_callable=AsyncMock)
    @patch("app.main.redis_client")
    @patch("app.main.async_session")
    @patch("app.main.engine")
    @patch("app.main.init_db", new_callable=AsyncMock)
    async def test_persisted_settings_override_rate_limit(
        self,
        mock_init_db: AsyncMock,
        mock_engine: MagicMock,
        mock_async_session: MagicMock,
        mock_redis: MagicMock,
        mock_seed_settings: AsyncMock,
        mock_banner: MagicMock,
        mock_load: MagicMock,
    ) -> None:
        from app.main import lifespan, rate_limit_config

        mock_conn = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_engine.begin.return_value = mock_cm

        mock_db = AsyncMock()
        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_cm.__aexit__ = AsyncMock(return_value=False)
        mock_async_session.return_value = mock_session_cm

        mock_redis.connected = True
        mock_redis.connect = AsyncMock()
        mock_redis.quit = AsyncMock()

        mock_load.return_value = RuntimeSettings(
            rate_limit={
                "RATE_LIMIT_ENABLED": "false",
                "RATE_LIMIT_MAX": "50",
                "RATE_LIMIT_WINDOW_MS": "30000",
            },
            redis={},
        )

        test_app = FastAPI()
        async with lifespan(test_app):
            assert not rate_limit_config.enabled
            assert rate_limit_config.max_requests == 50
            assert rate_limit_config.window_ms == 30000

    @patch("app.main.load_runtime_settings")
    @patch("app.main.print_banner")
    @patch("app.main.seed_settings", new_callable=AsyncMock)
    @patch("app.main.redis_client")
    @patch("app.main.async_session")
    @patch("app.main.engine")
    @patch("app.main.init_db", new_callable=AsyncMock)
    async def test_persisted_settings_override_redis(
        self,
        mock_init_db: AsyncMock,
        mock_engine: MagicMock,
        mock_async_session: MagicMock,
        mock_redis: MagicMock,
        mock_seed_settings: AsyncMock,
        mock_banner: MagicMock,
        mock_load: MagicMock,
    ) -> None:
        from app.main import lifespan

        mock_conn = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_engine.begin.return_value = mock_cm

        mock_db = AsyncMock()
        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_cm.__aexit__ = AsyncMock(return_value=False)
        mock_async_session.return_value = mock_session_cm

        mock_redis.connected = True
        mock_redis.connect = AsyncMock()
        mock_redis.quit = AsyncMock()

        mock_load.return_value = RuntimeSettings(
            rate_limit={},
            redis={
                "REDIS_HOST": "10.0.0.1",
                "REDIS_PORT": "6380",
                "REDIS_DB": "1",
                "REDIS_PASSWORD": "secret",
            },
        )

        test_app = FastAPI()
        async with lifespan(test_app):
            mock_redis.connect.assert_called_once_with(
                {
                    "host": "10.0.0.1",
                    "port": 6380,
                    "db": 1,
                    "password": "secret",
                }
            )

    @patch("app.main.load_runtime_settings")
    @patch("app.main.print_banner")
    @patch("app.main.seed_settings", new_callable=AsyncMock)
    @patch("app.main.redis_client")
    @patch("app.main.async_session")
    @patch("app.main.engine")
    @patch("app.main.init_db", new_callable=AsyncMock)
    async def test_persisted_settings_redis_url(
        self,
        mock_init_db: AsyncMock,
        mock_engine: MagicMock,
        mock_async_session: MagicMock,
        mock_redis: MagicMock,
        mock_seed_settings: AsyncMock,
        mock_banner: MagicMock,
        mock_load: MagicMock,
    ) -> None:
        from app.main import lifespan

        mock_conn = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_engine.begin.return_value = mock_cm

        mock_db = AsyncMock()
        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_cm.__aexit__ = AsyncMock(return_value=False)
        mock_async_session.return_value = mock_session_cm

        mock_redis.connected = True
        mock_redis.connect = AsyncMock()
        mock_redis.quit = AsyncMock()

        mock_load.return_value = RuntimeSettings(
            rate_limit={},
            redis={
                "REDIS_URL": "redis://user:pass@10.0.0.1:6380/2",
            },
        )

        test_app = FastAPI()
        async with lifespan(test_app):
            mock_redis.connect.assert_called_once_with(
                {
                    "url": "redis://user:pass@10.0.0.1:6380/2",
                }
            )
