from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.middleware.auth import (
    _AUTH_CACHE_TTL_S,
    _auth_cache,
    _get_cached_auth,
    _set_cached_auth,
    check_admin_auth,
    reset_auth_cache,
)
from app.models import Setting


@pytest.fixture(autouse=True)
def _reset_cache() -> None:
    reset_auth_cache()
    yield
    reset_auth_cache()


@pytest.fixture(autouse=True)
def _set_admin_key() -> None:
    old = settings.ADMIN_KEY
    settings.ADMIN_KEY = "test-admin-key"
    yield
    settings.ADMIN_KEY = old


class TestGetCachedAuth:
    def test_no_entry_returns_none(self) -> None:
        assert _get_cached_auth("nonexistent") is None

    def test_valid_entry_returns_true(self) -> None:
        _auth_cache["tok"] = (time.monotonic(), True)
        assert _get_cached_auth("tok") is True

    def test_valid_entry_returns_false(self) -> None:
        _auth_cache["tok"] = (time.monotonic(), False)
        assert _get_cached_auth("tok") is False

    def test_expired_entry_deleted(self) -> None:
        _auth_cache["tok"] = (time.monotonic() - _AUTH_CACHE_TTL_S - 1, True)
        assert _get_cached_auth("tok") is None
        assert "tok" not in _auth_cache

    def test_move_to_end_on_access(self) -> None:
        _auth_cache["a"] = (time.monotonic(), True)
        _auth_cache["b"] = (time.monotonic(), True)
        _get_cached_auth("a")
        assert list(_auth_cache.keys()) == ["b", "a"]


class TestSetCachedAuth:
    def test_adds_entry(self) -> None:
        _set_cached_auth("tok", True)
        assert "tok" in _auth_cache
        assert _auth_cache["tok"][1] is True

    def test_evicts_oldest_when_full(self) -> None:
        with patch("app.middleware.auth._AUTH_CACHE_MAX", 2):
            _set_cached_auth("a", True)
            _set_cached_auth("b", True)
            assert len(_auth_cache) == 2
            _set_cached_auth("c", True)
            assert len(_auth_cache) == 2
            assert "a" not in _auth_cache
            assert "c" in _auth_cache

    def test_removes_expired_before_evict(self) -> None:
        with patch("app.middleware.auth._AUTH_CACHE_MAX", 2):
            _auth_cache["old"] = (time.monotonic() - _AUTH_CACHE_TTL_S - 1, True)
            _auth_cache["keep"] = (time.monotonic(), True)
            _set_cached_auth("new", True)
            assert "old" not in _auth_cache
            assert len(_auth_cache) == 2


class TestResetAuthCache:
    def test_clears_all(self) -> None:
        _auth_cache["x"] = (time.monotonic(), True)
        _auth_cache["y"] = (time.monotonic(), False)
        reset_auth_cache()
        assert len(_auth_cache) == 0


class TestCheckAdminAuth:
    async def test_no_admin_key_returns_false(self) -> None:
        settings.ADMIN_KEY = ""
        mock_req = MagicMock()
        mock_req.headers = {"authorization": "Bearer test-admin-key"}
        mock_db = AsyncMock()
        result = await check_admin_auth(mock_req, mock_db)
        assert result is False

    async def test_no_auth_header_returns_false(self) -> None:
        mock_req = MagicMock()
        mock_req.headers = {}
        mock_db = AsyncMock()
        result = await check_admin_auth(mock_req, mock_db)
        assert result is False

    async def test_token_prefix_returns_false(self) -> None:
        mock_req = MagicMock()
        mock_req.headers = {"authorization": "Token test-admin-key"}
        mock_db = AsyncMock()
        result = await check_admin_auth(mock_req, mock_db)
        assert result is False

    async def test_valid_bearer_token(self, seed_test_data: AsyncSession) -> None:
        mock_req = MagicMock()
        mock_req.headers = {"authorization": "Bearer test-admin-key"}
        result = await check_admin_auth(mock_req, seed_test_data)
        assert result is True

    async def test_wrong_token_returns_false(self, seed_test_data: AsyncSession) -> None:
        mock_req = MagicMock()
        mock_req.headers = {"authorization": "Bearer wrong-token-value"}
        result = await check_admin_auth(mock_req, seed_test_data)
        assert result is False

    async def test_no_admin_key_setting_in_db(self, test_db: AsyncSession) -> None:
        await test_db.execute(Setting.__table__.delete().where(Setting.key == "ADMIN_KEY"))
        await test_db.commit()
        mock_req = MagicMock()
        mock_req.headers = {"authorization": "Bearer some-token"}
        result = await check_admin_auth(mock_req, test_db)
        assert result is False

    async def test_caches_valid_result(self, seed_test_data: AsyncSession) -> None:
        mock_req = MagicMock()
        mock_req.headers = {"authorization": "Bearer test-admin-key"}
        r1 = await check_admin_auth(mock_req, seed_test_data)
        assert r1 is True
        assert _get_cached_auth("test-admin-key") is True

    async def test_caches_invalid_result(self, seed_test_data: AsyncSession) -> None:
        mock_req = MagicMock()
        mock_req.headers = {"authorization": "Bearer bad-token"}
        r1 = await check_admin_auth(mock_req, seed_test_data)
        assert r1 is False
        assert _get_cached_auth("bad-token") is False

    async def test_db_exception_returns_false(self, seed_test_data: AsyncSession) -> None:
        mock_req = MagicMock()
        mock_req.headers = {"authorization": "Bearer test-admin-key"}
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=Exception("db error"))
        result = await check_admin_auth(mock_req, mock_db)
        assert result is False

    async def test_cache_hit_returns_cached_value(self, seed_test_data: AsyncSession) -> None:
        from app.middleware.auth import reset_auth_cache

        reset_auth_cache()
        mock_req = MagicMock()
        mock_req.headers = {"authorization": "Bearer test-admin-key"}
        r1 = await check_admin_auth(mock_req, seed_test_data)
        assert r1 is True
        mock_db2 = AsyncMock()
        r2 = await check_admin_auth(mock_req, mock_db2)
        assert r2 is True
        mock_db2.execute.assert_not_called()
        assert _get_cached_auth("test-admin-key") is True
