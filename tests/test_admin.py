from __future__ import annotations

import logging
from typing import Any

import httpx
import pytest


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


class TestAdminSettingsUnauthorized:
    async def test_get_settings_no_auth(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/admin/settings")
        assert resp.status_code == 401

    async def test_get_settings_wrong_token(self, client: httpx.AsyncClient) -> None:
        resp = await client.get(
            "/api/admin/settings",
            headers={
                "Authorization": "Bearer wrong-token",
            },
        )
        assert resp.status_code == 401


class TestAdminSettingsAuthorized:
    async def test_get_settings_with_auth(self, client: httpx.AsyncClient) -> None:
        resp = await client.get(
            "/api/admin/settings",
            headers={
                "Authorization": "Bearer test-admin-key",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) > 0

        keys = {s["key"] for s in data}
        assert "ADMIN_KEY" in keys
        assert "APP_ENV" in keys

    async def test_sensitive_keys_masked(self, client: httpx.AsyncClient) -> None:
        resp = await client.get(
            "/api/admin/settings",
            headers={
                "Authorization": "Bearer test-admin-key",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        admin_key = next(s for s in data if s["key"] == "ADMIN_KEY")
        assert admin_key["value"] == "***"

    async def test_patch_setting(self, client: httpx.AsyncClient) -> None:
        resp = await client.patch(
            "/api/admin/settings/PORT",
            json={
                "value": "4000",
            },
            headers={
                "Authorization": "Bearer test-admin-key",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["key"] == "PORT"
        assert data["value"] == "4000"


class TestAdminInvalidSettings:
    async def test_unknown_setting_returns_404(self, client: httpx.AsyncClient) -> None:
        resp = await client.patch(
            "/api/admin/settings/UNKNOWN_KEY",
            json={"value": "test"},
            headers={
                "Authorization": "Bearer test-admin-key",
            },
        )
        assert resp.status_code == 404

    async def test_redis_port_out_of_range(self, client: httpx.AsyncClient) -> None:
        resp = await client.patch(
            "/api/admin/settings/REDIS_PORT",
            json={"value": 99999},
            headers={
                "Authorization": "Bearer test-admin-key",
            },
        )
        assert resp.status_code == 400

    async def test_setting_with_null_value(self, client: httpx.AsyncClient) -> None:
        resp = await client.patch(
            "/api/admin/settings/PORT",
            json={"value": None},
            headers={
                "Authorization": "Bearer test-admin-key",
            },
        )
        assert resp.status_code == 400

    async def test_setting_with_dict_value(self, client: httpx.AsyncClient) -> None:
        resp = await client.patch(
            "/api/admin/settings/PORT",
            json={"value": {}},
            headers={
                "Authorization": "Bearer test-admin-key",
            },
        )
        assert resp.status_code == 400

    async def test_boolean_invalid_string(self, client: httpx.AsyncClient) -> None:
        resp = await client.patch(
            "/api/admin/settings/RATE_LIMIT_ENABLED",
            json={"value": "invalid"},
            headers={
                "Authorization": "Bearer test-admin-key",
            },
        )
        assert resp.status_code == 400

    async def test_patch_setting_valid_persists(self, client: httpx.AsyncClient) -> None:
        resp = await client.patch(
            "/api/admin/settings/RATE_LIMIT_MAX",
            json={"value": 200},
            headers={
                "Authorization": "Bearer test-admin-key",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["key"] == "RATE_LIMIT_MAX"
        assert data["value"] == "200"


class TestAdminInvalidJsonBody:
    async def test_patch_empty_body_returns_400(self, client: httpx.AsyncClient) -> None:
        resp = await client.patch(
            "/api/admin/settings/PORT",
            content=b"",
            headers={
                "Authorization": "Bearer test-admin-key",
                "Content-Type": "application/json",
            },
        )
        assert resp.status_code == 400

    async def test_patch_invalid_json_returns_400(self, client: httpx.AsyncClient) -> None:
        resp = await client.patch(
            "/api/admin/settings/PORT",
            content=b"not json",
            headers={
                "Authorization": "Bearer test-admin-key",
                "Content-Type": "application/json",
            },
        )
        assert resp.status_code == 400

    async def test_patch_missing_value_field_returns_400(self, client: httpx.AsyncClient) -> None:
        resp = await client.patch(
            "/api/admin/settings/PORT",
            json={"other": "x"},
            headers={
                "Authorization": "Bearer test-admin-key",
            },
        )
        assert resp.status_code == 400

    async def test_reset_empty_body_returns_400(self, client: httpx.AsyncClient) -> None:
        resp = await client.post(
            "/api/admin/reset-database",
            content=b"",
            headers={
                "Authorization": "Bearer test-admin-key",
                "Content-Type": "application/json",
            },
        )
        assert resp.status_code == 400

    async def test_reset_invalid_json_returns_400(self, client: httpx.AsyncClient) -> None:
        resp = await client.post(
            "/api/admin/reset-database",
            content=b"not json",
            headers={
                "Authorization": "Bearer test-admin-key",
                "Content-Type": "application/json",
            },
        )
        assert resp.status_code == 400


class TestAdminDebugSql:
    async def test_patch_debug_sql_true_enables_echo(self, client: httpx.AsyncClient) -> None:
        from app.database import engine

        try:
            resp = await client.patch(
                "/api/admin/settings/DEBUG_SQL",
                json={"value": True},
                headers={"Authorization": "Bearer test-admin-key"},
            )
            assert resp.status_code in (200, 201)
            assert engine.echo is True
        finally:
            engine.echo = False

    async def test_patch_debug_sql_false_disables_echo(self, client: httpx.AsyncClient) -> None:
        from app.database import engine

        try:
            resp = await client.patch(
                "/api/admin/settings/DEBUG_SQL",
                json={"value": False},
                headers={"Authorization": "Bearer test-admin-key"},
            )
            assert resp.status_code in (200, 201)
            assert engine.echo is False
        finally:
            engine.echo = False

    async def test_patch_debug_sql_invalid_value_returns_400(
        self, client: httpx.AsyncClient
    ) -> None:
        resp = await client.patch(
            "/api/admin/settings/DEBUG_SQL",
            json={"value": "yes"},
            headers={"Authorization": "Bearer test-admin-key"},
        )
        assert resp.status_code == 400


class TestAdminDefaultPageSize:
    async def test_patch_default_page_size_changes_pagination(
        self, client: httpx.AsyncClient
    ) -> None:
        resp = await client.patch(
            "/api/admin/settings/DEFAULT_PAGE_SIZE",
            json={"value": 2},
            headers={"Authorization": "Bearer test-admin-key"},
        )
        assert resp.status_code in (200, 201)

        list_resp = await client.get("/api/posts")
        assert list_resp.status_code == 200
        assert len(list_resp.json()) == 2


class TestAdminResetDatabase:
    async def test_reset_without_confirm(self, client: httpx.AsyncClient) -> None:
        resp = await client.post(
            "/api/admin/reset-database",
            json={},
            headers={
                "Authorization": "Bearer test-admin-key",
            },
        )
        assert resp.status_code == 400

    async def test_reset_without_auth(self, client: httpx.AsyncClient) -> None:
        resp = await client.post(
            "/api/admin/reset-database",
            json={
                "confirm": True,
            },
        )
        assert resp.status_code == 401

    async def test_reset_rejects_non_object_body(self, client: httpx.AsyncClient) -> None:
        resp = await client.post(
            "/api/admin/reset-database",
            json=[],
            headers={
                "Authorization": "Bearer test-admin-key",
            },
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "JSON body must be an object"


class TestUpdateSettingCleanSession:
    async def test_no_trailing_rollback_after_successful_patch(
        self, client: httpx.AsyncClient, test_engine: Any, caplog: Any
    ) -> None:
        caplog.set_level(logging.INFO, logger="sqlalchemy.engine.Engine")
        try:
            test_engine.echo = True
            resp = await client.patch(
                "/api/admin/settings/DEBUG_SQL",
                json={"value": True},
                headers={"Authorization": "Bearer test-admin-key"},
            )
            assert resp.status_code in (200, 201)

            msgs = [r.getMessage() for r in caplog.records if r.name == "sqlalchemy.engine.Engine"]
            assert msgs, "expected SQLAlchemy engine log records for the request"
            assert "COMMIT" in msgs, "the setting write must be committed"
            assert msgs[-1] == "COMMIT", (
                "session should close cleanly right after COMMIT with no trailing "
                f"ROLLBACK; last engine log was {msgs[-1]!r}"
            )
        finally:
            test_engine.echo = False


class TestAdminApplyFailure:
    async def test_rate_limit_apply_failure_returns_503(
        self, test_app: Any, client: httpx.AsyncClient
    ) -> None:
        from unittest.mock import patch

        from app.services.runtime_config import RateLimitConfig

        with patch.object(RateLimitConfig, "update", side_effect=RuntimeError("apply failed")):
            resp = await client.patch(
                "/api/admin/settings/RATE_LIMIT_ENABLED",
                json={"value": "false"},
                headers={"Authorization": "Bearer test-admin-key"},
            )
            assert resp.status_code == 503
            assert "detail" in resp.json()

        resp2 = await client.get(
            "/api/admin/settings",
            headers={"Authorization": "Bearer test-admin-key"},
        )
        data2 = resp2.json()
        setting = next(s for s in data2 if s["key"] == "RATE_LIMIT_ENABLED")
        assert setting["value"] == "true"

        assert test_app.state.rate_limit_config.enabled is True

    async def test_redis_reconnect_failure_returns_503(
        self, test_app: Any, client: httpx.AsyncClient
    ) -> None:
        from unittest.mock import AsyncMock

        mock_redis = AsyncMock()
        mock_redis.reconnect = AsyncMock(side_effect=RuntimeError("reconnect failed"))
        test_app.state.redis_client = mock_redis

        resp = await client.patch(
            "/api/admin/settings/REDIS_HOST",
            json={"value": "newhost"},
            headers={"Authorization": "Bearer test-admin-key"},
        )
        assert resp.status_code == 503
        assert "detail" in resp.json()

        resp2 = await client.get(
            "/api/admin/settings",
            headers={"Authorization": "Bearer test-admin-key"},
        )
        data2 = resp2.json()
        setting = next(s for s in data2 if s["key"] == "REDIS_HOST")
        assert setting["value"] == "127.0.0.1"

    async def test_no_secret_in_response_on_failure(
        self, test_app: Any, client: httpx.AsyncClient
    ) -> None:
        from unittest.mock import AsyncMock

        mock_redis = AsyncMock()
        mock_redis.reconnect = AsyncMock(side_effect=RuntimeError("reconnect failed"))
        test_app.state.redis_client = mock_redis

        resp = await client.patch(
            "/api/admin/settings/REDIS_PASSWORD",
            json={"value": "super-secret-value"},
            headers={"Authorization": "Bearer test-admin-key"},
        )
        assert resp.status_code == 503
        assert "super-secret-value" not in resp.text
