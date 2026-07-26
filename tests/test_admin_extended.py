from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.routes.admin import (
    _apply_rate_limit_update,
    _apply_redis_update,
    _get_rate_limit_config,
    _get_redis_client,
    _mask_setting,
)


@pytest.fixture(autouse=True)
def _set_admin_key_env() -> None:
    from app.config import settings
    from app.middleware.auth import reset_auth_cache

    old_val = settings.ADMIN_KEY
    settings.ADMIN_KEY = "test-admin-key"
    reset_auth_cache()
    yield
    settings.ADMIN_KEY = old_val
    reset_auth_cache()


class TestMaskSetting:
    def test_mask_sensitive_key_admin_key(self, seed_test_data):
        from app.models import Setting

        row = Setting(
            id=1, key="ADMIN_KEY", value="hashed-secret", description="Admin key", updated_at="now"
        )
        result = _mask_setting(row)
        assert result["value"] == "***"
        assert result["key"] == "ADMIN_KEY"

    def test_mask_sensitive_key_redis_password(self, seed_test_data):
        from app.models import Setting

        row = Setting(
            id=2,
            key="REDIS_PASSWORD",
            value="secret-pass",
            description="Redis password",
            updated_at="now",
        )
        result = _mask_setting(row)
        assert result["value"] == "***"

    def test_mask_sensitive_key_redis_url(self, seed_test_data):
        from app.models import Setting

        row = Setting(
            id=3,
            key="REDIS_URL",
            value="redis://:secret@cache.internal:6379/0",
            description="Redis URL",
            updated_at="now",
        )
        result = _mask_setting(row)
        assert result["value"] == "***"

    def test_mask_non_sensitive_key(self, seed_test_data):
        from app.models import Setting

        row = Setting(id=4, key="PORT", value="3000", description="Port", updated_at="now")
        result = _mask_setting(row)
        assert result["value"] == "3000"

    def test_mask_setting_fields(self, seed_test_data):
        from app.models import Setting

        row = Setting(
            id=5, key="APP_ENV", value="production", description="Env", updated_at="2024-01-01"
        )
        result = _mask_setting(row)
        assert result["id"] == 5
        assert result["key"] == "APP_ENV"
        assert result["description"] == "Env"
        assert result["updated_at"] == "2024-01-01"


class TestApplyRateLimitUpdate:
    async def test_rate_limit_enabled_true(self):
        from app.services.runtime_config import RateLimitConfig

        config = RateLimitConfig(enabled=False, max_requests=100, window_ms=60000)
        await _apply_rate_limit_update("RATE_LIMIT_ENABLED", "true", config)
        assert config.enabled is True

    async def test_rate_limit_enabled_false(self):
        from app.services.runtime_config import RateLimitConfig

        config = RateLimitConfig(enabled=True, max_requests=100, window_ms=60000)
        await _apply_rate_limit_update("RATE_LIMIT_ENABLED", "false", config)
        assert config.enabled is False

    async def test_rate_limit_enabled_other(self):
        from app.services.runtime_config import RateLimitConfig

        config = RateLimitConfig(enabled=False, max_requests=100, window_ms=60000)
        await _apply_rate_limit_update("RATE_LIMIT_ENABLED", "yes", config)
        assert config.enabled is True

    async def test_rate_limit_max_valid(self):
        from app.services.runtime_config import RateLimitConfig

        config = RateLimitConfig(enabled=True, max_requests=100, window_ms=60000)
        await _apply_rate_limit_update("RATE_LIMIT_MAX", "200", config)
        assert config.max_requests == 200

    async def test_rate_limit_max_invalid(self):
        from app.services.runtime_config import RateLimitConfig

        config = RateLimitConfig(enabled=True, max_requests=100, window_ms=60000)
        await _apply_rate_limit_update("RATE_LIMIT_MAX", "not-a-number", config)
        assert config.max_requests == 100

    async def test_rate_limit_window_ms_valid(self):
        from app.services.runtime_config import RateLimitConfig

        config = RateLimitConfig(enabled=True, max_requests=100, window_ms=60000)
        await _apply_rate_limit_update("RATE_LIMIT_WINDOW_MS", "30000", config)
        assert config.window_ms == 30000

    async def test_rate_limit_window_ms_invalid(self):
        from app.services.runtime_config import RateLimitConfig

        config = RateLimitConfig(enabled=True, max_requests=100, window_ms=60000)
        await _apply_rate_limit_update("RATE_LIMIT_WINDOW_MS", "abc", config)
        assert config.window_ms == 60000

    async def test_no_update_fn(self):
        await _apply_rate_limit_update("RATE_LIMIT_ENABLED", "true", None)

    async def test_unknown_key_no_call(self):
        mock_fn = MagicMock()
        await _apply_rate_limit_update("UNKNOWN_KEY", "value", mock_fn)
        mock_fn.assert_not_called()


class TestApplyRedisUpdate:
    async def test_no_redis_client(self, test_db):
        await _apply_redis_update(None, test_db)

    async def test_with_redis_url(self, test_db):
        from app.models import Setting

        now = "2024-01-01T00:00:00"
        test_db.add(
            Setting(key="REDIS_URL", value="redis://localhost:6379", description="", updated_at=now)
        )
        await test_db.commit()

        mock_redis = AsyncMock()
        await _apply_redis_update(mock_redis, test_db)
        mock_redis.reconnect.assert_called_once()
        call_args = mock_redis.reconnect.call_args[0][0]
        assert call_args["url"] == "redis://localhost:6379"

    async def test_without_redis_url(self, test_db):
        from app.models import Setting

        now = "2024-01-01T00:00:00"
        test_db.add(Setting(key="REDIS_HOST", value="myhost", description="", updated_at=now))
        test_db.add(Setting(key="REDIS_PORT", value="6380", description="", updated_at=now))
        test_db.add(Setting(key="REDIS_DB", value="2", description="", updated_at=now))
        test_db.add(Setting(key="REDIS_PASSWORD", value="pw", description="", updated_at=now))
        await test_db.commit()

        mock_redis = AsyncMock()
        await _apply_redis_update(mock_redis, test_db)
        mock_redis.reconnect.assert_called_once()
        call_args = mock_redis.reconnect.call_args[0][0]
        assert call_args["host"] == "myhost"
        assert call_args["port"] == 6380
        assert call_args["db"] == 2
        assert call_args["password"] == "pw"

    async def test_without_redis_url_defaults(self, test_db):
        mock_redis = AsyncMock()
        await _apply_redis_update(mock_redis, test_db)
        mock_redis.reconnect.assert_called_once()
        call_args = mock_redis.reconnect.call_args[0][0]
        assert call_args["host"] == "127.0.0.1"
        assert call_args["port"] == 6379
        assert call_args["db"] == 0
        assert call_args["password"] is None

    async def test_redis_url_takes_priority(self, test_db):
        from app.models import Setting

        now = "2024-01-01T00:00:00"
        test_db.add(
            Setting(key="REDIS_URL", value="redis://custom:9999", description="", updated_at=now)
        )
        test_db.add(Setting(key="REDIS_HOST", value="other-host", description="", updated_at=now))
        await test_db.commit()

        mock_redis = AsyncMock()
        await _apply_redis_update(mock_redis, test_db)
        mock_redis.reconnect.assert_called_once()
        call_args = mock_redis.reconnect.call_args[0][0]
        assert "url" in call_args
        assert "host" not in call_args


class TestAdminSettingsRoute:
    async def test_list_settings_masks_admin_key(self, client: httpx.AsyncClient):
        resp = await client.get(
            "/api/admin/settings", headers={"Authorization": "Bearer test-admin-key"}
        )
        assert resp.status_code == 200
        data = resp.json()
        admin = next(s for s in data if s["key"] == "ADMIN_KEY")
        assert admin["value"] == "***"

    async def test_list_settings_masks_redis_password(self, client: httpx.AsyncClient):
        resp = await client.get(
            "/api/admin/settings", headers={"Authorization": "Bearer test-admin-key"}
        )
        assert resp.status_code == 200
        data = resp.json()
        rp = next(s for s in data if s["key"] == "REDIS_PASSWORD")
        assert rp["value"] == "***"

    async def test_list_settings_no_auth(self, client: httpx.AsyncClient):
        resp = await client.get("/api/admin/settings")
        assert resp.status_code == 401


class TestUpdateSettingRoute:
    async def test_create_new_setting(self, client: httpx.AsyncClient):
        resp = await client.patch(
            "/api/admin/settings/DEFAULT_PAGE_SIZE",
            json={"value": "50"},
            headers={"Authorization": "Bearer test-admin-key"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["key"] == "DEFAULT_PAGE_SIZE"
        assert data["value"] == "50"
        assert data["id"] > 0

    async def test_create_setting_returns_201(self, client: httpx.AsyncClient):
        resp = await client.patch(
            "/api/admin/settings/DB_PATH",
            json={"value": "/tmp/test.db"},
            headers={"Authorization": "Bearer test-admin-key"},
        )
        assert resp.status_code == 201
        assert resp.json()["value"] == "/tmp/test.db"

    async def test_update_existing_setting_returns_200(self, client: httpx.AsyncClient):
        resp = await client.patch(
            "/api/admin/settings/PORT",
            json={"value": "4000"},
            headers={"Authorization": "Bearer test-admin-key"},
        )
        assert resp.status_code == 200

    async def test_update_admin_key_never_returns_hash(self, client: httpx.AsyncClient):
        resp = await client.patch(
            "/api/admin/settings/ADMIN_KEY",
            json={"value": "new-secret"},
            headers={"Authorization": "Bearer test-admin-key"},
        )
        assert resp.status_code == 200
        assert resp.json()["value"] == "***"
        assert "new-secret" not in resp.text

    async def test_update_redis_password_never_returns_secret(
        self, client: httpx.AsyncClient, test_db
    ):
        resp = await client.patch(
            "/api/admin/settings/REDIS_PASSWORD",
            json={"value": "redis-secret"},
            headers={"Authorization": "Bearer test-admin-key"},
        )
        assert resp.status_code in {200, 201}
        assert resp.json()["value"] == "***"
        assert "redis-secret" not in resp.text

    async def test_update_admin_key_hashes_value(self, client: httpx.AsyncClient):
        resp = await client.patch(
            "/api/admin/settings/ADMIN_KEY",
            json={"value": "new-secret-key"},
            headers={"Authorization": "Bearer test-admin-key"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["key"] == "ADMIN_KEY"
        assert data["value"] != "new-secret-key"

    async def test_update_setting_none_value(self, client: httpx.AsyncClient):
        resp = await client.patch(
            "/api/admin/settings/PORT",
            json={"value": None},
            headers={"Authorization": "Bearer test-admin-key"},
        )
        assert resp.status_code == 400

    async def test_update_setting_dict_value(self, client: httpx.AsyncClient):
        resp = await client.patch(
            "/api/admin/settings/PORT",
            json={"value": {"a": 1}},
            headers={"Authorization": "Bearer test-admin-key"},
        )
        assert resp.status_code == 400

    async def test_update_setting_list_value(self, client: httpx.AsyncClient):
        resp = await client.patch(
            "/api/admin/settings/PORT",
            json={"value": [1, 2, 3]},
            headers={"Authorization": "Bearer test-admin-key"},
        )
        assert resp.status_code == 400

    async def test_update_setting_missing_value_key(self, client: httpx.AsyncClient):
        resp = await client.patch(
            "/api/admin/settings/PORT",
            json={"other": "data"},
            headers={"Authorization": "Bearer test-admin-key"},
        )
        assert resp.status_code == 400

    async def test_update_setting_no_auth(self, client: httpx.AsyncClient):
        resp = await client.patch("/api/admin/settings/PORT", json={"value": "4000"})
        assert resp.status_code == 401

    async def test_update_setting_rate_limit_enabled(self, test_app, client: httpx.AsyncClient):
        resp = await client.patch(
            "/api/admin/settings/RATE_LIMIT_ENABLED",
            json={"value": "false"},
            headers={"Authorization": "Bearer test-admin-key"},
        )
        assert resp.status_code == 200
        assert test_app.state.rate_limit_config.enabled is False

    async def test_update_setting_rate_limit_max(self, test_app, client: httpx.AsyncClient):
        resp = await client.patch(
            "/api/admin/settings/RATE_LIMIT_MAX",
            json={"value": "500"},
            headers={"Authorization": "Bearer test-admin-key"},
        )
        assert resp.status_code == 200
        assert test_app.state.rate_limit_config.max_requests == 500

    async def test_update_setting_rate_limit_window_ms(self, test_app, client: httpx.AsyncClient):
        resp = await client.patch(
            "/api/admin/settings/RATE_LIMIT_WINDOW_MS",
            json={"value": "120000"},
            headers={"Authorization": "Bearer test-admin-key"},
        )
        assert resp.status_code == 200
        assert test_app.state.rate_limit_config.window_ms == 120000

    async def test_update_setting_redis_host(self, test_app, client: httpx.AsyncClient):
        mock_redis = AsyncMock()
        test_app.state.redis_client = mock_redis
        resp = await client.patch(
            "/api/admin/settings/REDIS_HOST",
            json={"value": "newhost"},
            headers={"Authorization": "Bearer test-admin-key"},
        )
        assert resp.status_code == 200
        mock_redis.reconnect.assert_called_once()


class TestResetDatabase:
    async def test_reset_success(self, client: httpx.AsyncClient):
        with (
            patch("app.routes.admin.fetch_seed_payload", new_callable=AsyncMock) as mock_fetch,
            patch("app.routes.admin.apply_seed_payload", new_callable=AsyncMock) as mock_apply,
        ):
            mock_fetch.return_value = {
                "users": [],
                "posts": [],
                "comments": [],
                "albums": [],
                "photos": [],
                "todos": [],
            }
            resp = await client.post(
                "/api/admin/reset-database",
                json={"confirm": True},
                headers={"Authorization": "Bearer test-admin-key"},
            )
            assert resp.status_code == 200
            assert resp.json()["message"] == "Database reset and re-seeded successfully"
            mock_fetch.assert_called_once()
            mock_apply.assert_called_once()

    async def test_reset_no_confirm(self, client: httpx.AsyncClient):
        resp = await client.post(
            "/api/admin/reset-database",
            json={"confirm": False},
            headers={"Authorization": "Bearer test-admin-key"},
        )
        assert resp.status_code == 400

    async def test_reset_no_auth(self, client: httpx.AsyncClient):
        resp = await client.post("/api/admin/reset-database", json={"confirm": True})
        assert resp.status_code == 401

    async def test_reset_empty_body(self, client: httpx.AsyncClient):
        resp = await client.post(
            "/api/admin/reset-database", json={}, headers={"Authorization": "Bearer test-admin-key"}
        )
        assert resp.status_code == 400


class TestHelperFunctions:
    async def test_get_rate_limit_config(self, test_app):
        from starlette.requests import Request

        scope = {"type": "http", "method": "GET", "path": "/", "headers": [], "app": test_app}
        request = Request(scope)
        result = await _get_rate_limit_config(request)
        assert result.enabled is True
        assert result.max_requests == 100

    async def test_get_redis_client(self, test_app):
        from starlette.requests import Request

        scope = {"type": "http", "method": "GET", "path": "/", "headers": [], "app": test_app}
        request = Request(scope)
        result = await _get_redis_client(request)
        assert result is None


class TestUpdateSettingExceptions:
    async def test_update_rate_limit_exception_handled(self, test_app, client: httpx.AsyncClient):
        from app.services.runtime_config import RateLimitConfig

        with patch.object(RateLimitConfig, "update", side_effect=RuntimeError("update failed")):
            resp = await client.patch(
                "/api/admin/settings/RATE_LIMIT_ENABLED",
                json={"value": "false"},
                headers={"Authorization": "Bearer test-admin-key"},
            )
            assert resp.status_code == 503

    async def test_update_redis_exception_handled(self, test_app, client: httpx.AsyncClient):
        mock_redis = AsyncMock()
        mock_redis.reconnect = AsyncMock(side_effect=RuntimeError("redis error"))
        test_app.state.redis_client = mock_redis
        resp = await client.patch(
            "/api/admin/settings/REDIS_HOST",
            json={"value": "newhost"},
            headers={"Authorization": "Bearer test-admin-key"},
        )
        assert resp.status_code == 503


async def count_all_resources(db) -> dict[str, int]:
    from sqlalchemy import select

    from app.models import Album, Comment, Photo, Post, Todo, User

    counts: dict[str, int] = {}
    for model, name in [
        (User, "users"),
        (Post, "posts"),
        (Comment, "comments"),
        (Album, "albums"),
        (Photo, "photos"),
        (Todo, "todos"),
    ]:
        result = await db.execute(select(model))
        rows = result.scalars().all()
        counts[name] = len(rows)
    return counts


class TestResetDatabaseAtomicity:
    async def test_reset_fetch_failure_preserves_existing_rows(self, client, test_db, monkeypatch):
        before = await count_all_resources(test_db)

        async def fail_fetch(*args, **kwargs):
            raise RuntimeError("upstream unavailable")

        monkeypatch.setattr("app.routes.admin.fetch_seed_payload", fail_fetch)

        response = await client.post(
            "/api/admin/reset-database",
            json={"confirm": True},
            headers={"Authorization": "Bearer test-admin-key"},
        )

        assert response.status_code == 502
        assert await count_all_resources(test_db) == before

    async def test_reset_insert_failure_rolls_back_deletes(self, client, test_db, monkeypatch):
        before = await count_all_resources(test_db)

        async def fail_apply(*args, **kwargs):
            raise RuntimeError("insert failed")

        monkeypatch.setattr("app.routes.admin.apply_seed_payload", fail_apply)

        response = await client.post(
            "/api/admin/reset-database",
            json={"confirm": True},
            headers={"Authorization": "Bearer test-admin-key"},
        )

        assert response.status_code == 500
        assert await count_all_resources(test_db) == before


class TestResetLockTimeout:
    async def test_reset_lock_timeout(self, client: httpx.AsyncClient):
        import app.routes.admin as admin_mod

        original_timeout = admin_mod.RESET_LOCK_TIMEOUT_S
        admin_mod.RESET_LOCK_TIMEOUT_S = 0.001
        original_lock = admin_mod._reset_lock

        class FakeLock:
            async def acquire(self):

                await asyncio.sleep(100)

            def release(self):
                pass

        admin_mod._reset_lock = FakeLock()
        try:
            resp = await client.post(
                "/api/admin/reset-database",
                json={"confirm": True},
                headers={"Authorization": "Bearer test-admin-key"},
            )
            assert resp.status_code == 503
        finally:
            admin_mod._reset_lock = original_lock
            admin_mod.RESET_LOCK_TIMEOUT_S = original_timeout


class TestIntegration:
    async def test_admin_rate_limit_update_changes_middleware_behavior(self, client, test_app):
        response = await client.patch(
            "/api/admin/settings/RATE_LIMIT_MAX",
            json={"value": "1"},
            headers={"Authorization": "Bearer test-admin-key"},
        )
        assert response.status_code == 200
        assert test_app.state.rate_limit_config.max_requests == 1
