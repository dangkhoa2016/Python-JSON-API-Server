from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from argon2 import PasswordHasher
from sqlalchemy import event as sa_event
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.database import get_db, init_db
from app.models import Base, Setting, User
from app.services.runtime_config import RateLimitConfig
from app.services.runtime_settings import load_runtime_settings
from app.services.seed import add_seed_rows, apply_seed_payload, fetch_seed_payload, seed
from app.services.seed_settings import SETTING_DEFS, seed_settings


class TestRateLimitConfig:
    def test_initial_values(self) -> None:
        rc = RateLimitConfig(enabled=True, max_requests=100, window_ms=60000)
        assert rc.enabled is True
        assert rc.max_requests == 100
        assert rc.window_ms == 60000

    def test_update_enabled(self) -> None:
        rc = RateLimitConfig(enabled=True, max_requests=100, window_ms=60000)
        rc.update({"enabled": False})
        assert rc.enabled is False
        rc.update({"enabled": True})
        assert rc.enabled is True

    def test_update_max(self) -> None:
        rc = RateLimitConfig(enabled=True, max_requests=100, window_ms=60000)
        rc.update({"max": 200})
        assert rc.max_requests == 200

    def test_update_max_clamps_to_min_one(self) -> None:
        rc = RateLimitConfig(enabled=True, max_requests=100, window_ms=60000)
        rc.update({"max": 0})
        assert rc.max_requests == 1

    def test_update_window_ms(self) -> None:
        rc = RateLimitConfig(enabled=True, max_requests=100, window_ms=60000)
        rc.update({"windowMs": 30000})
        assert rc.window_ms == 30000

    def test_update_window_ms_clamps_to_min_1000(self) -> None:
        rc = RateLimitConfig(enabled=True, max_requests=100, window_ms=60000)
        rc.update({"windowMs": 100})
        assert rc.window_ms == 1000

    def test_update_unrelated_keys_ignored(self) -> None:
        rc = RateLimitConfig(enabled=True, max_requests=100, window_ms=60000)
        rc.update({"unrelated": "value"})
        assert rc.enabled is True
        assert rc.max_requests == 100
        assert rc.window_ms == 60000

    def test_update_multiple_keys(self) -> None:
        rc = RateLimitConfig(enabled=True, max_requests=100, window_ms=60000)
        rc.update({"enabled": False, "max": 50, "windowMs": 120000})
        assert rc.enabled is False
        assert rc.max_requests == 50
        assert rc.window_ms == 120000


class TestRateLimitWindowSec:
    def test_exact_seconds(self) -> None:
        s = Settings(RATE_LIMIT_WINDOW_MS=60000)
        assert s.rate_limit_window_sec == 60

    def test_ceiling_division(self) -> None:
        s = Settings(RATE_LIMIT_WINDOW_MS=65001)
        assert s.rate_limit_window_sec == 66

    def test_small_value(self) -> None:
        s = Settings(RATE_LIMIT_WINDOW_MS=100)
        assert s.rate_limit_window_sec == 1

    def test_zero(self) -> None:
        s = Settings(RATE_LIMIT_WINDOW_MS=0)
        assert s.rate_limit_window_sec == 0


class TestRedisOpts:
    def test_with_redis_url(self) -> None:
        s = Settings(REDIS_URL="redis://localhost:6379/0")
        assert s.redis_opts == {"url": "redis://localhost:6379/0"}

    def test_without_redis_url(self) -> None:
        s = Settings(
            REDIS_URL=None,
            REDIS_HOST="myhost",
            REDIS_PORT=6380,
            REDIS_DB=2,
            REDIS_PASSWORD="secret",
        )
        assert s.redis_opts == {
            "host": "myhost",
            "port": 6380,
            "db": 2,
            "password": "secret",
        }

    def test_without_redis_url_defaults(self) -> None:
        s = Settings(REDIS_URL=None, REDIS_PASSWORD=None)
        opts = s.redis_opts
        assert opts["host"] == "127.0.0.1"
        assert opts["port"] == 6379
        assert opts["db"] == 0
        assert opts["password"] is None


class TestSeedSettings:
    async def test_seed_settings_empty_db(self, test_db) -> None:
        result = await seed_settings(test_db)
        assert result == 14

        row = await test_db.execute(text("SELECT COUNT(*) FROM settings"))
        assert row.scalar_one() == 14

        row = await test_db.execute(text("SELECT key FROM settings ORDER BY id"))
        keys = [r[0] for r in row.fetchall()]
        expected_keys = [d["key"] for d in SETTING_DEFS]
        assert keys == expected_keys

    async def test_seed_settings_already_seeded(self, test_db) -> None:
        await seed_settings(test_db)
        result = await seed_settings(test_db)
        assert result == 0

    async def test_seed_settings_hashes_admin_key_when_env_set(self, test_db) -> None:
        from sqlalchemy import text as sa_text

        await test_db.execute(sa_text("DELETE FROM settings"))
        await test_db.commit()
        config = Settings(ADMIN_KEY="my-secret-admin-key")
        count = await seed_settings(test_db, config)
        assert count > 0
        row = await test_db.execute(select(Setting).where(Setting.key == "ADMIN_KEY"))
        admin = row.scalar_one()
        ph = PasswordHasher()
        assert ph.verify(admin.value, "my-secret-admin-key")


class TestSeed:
    async def test_seed_already_has_users(self, test_db) -> None:
        test_db.add(User(id=1, name="Existing"))
        await test_db.flush()
        result = await seed(test_db)
        assert result == 0

    @patch("app.services.seed.httpx.AsyncClient")
    async def test_seed_empty_db(self, MockAsyncClient, test_db) -> None:
        users_data = [
            {
                "id": 1,
                "name": "A",
                "username": "a",
                "email": "a@b.com",
                "phone": "1",
                "website": "a.com",
                "address": json.dumps({"city": "X"}),
                "company": json.dumps({"name": "Y"}),
            },
        ]
        posts_data = [{"id": 1, "userId": 1, "title": "t", "body": "b"}]
        comments_data = [{"id": 1, "postId": 1, "name": "c", "email": "c@x.com", "body": "cb"}]
        albums_data = [{"id": 1, "userId": 1, "title": "al"}]
        photos_data = [{"id": 1, "albumId": 1, "title": "ph", "url": "u", "thumbnailUrl": "tu"}]
        todos_data = [{"id": 1, "userId": 1, "title": "td", "completed": True}]

        responses = [users_data, posts_data, comments_data, albums_data, photos_data, todos_data]

        class FakeClient:
            def __init__(self, **kwargs):
                self._idx = 0

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def get(self, url):
                r = MagicMock()
                r.raise_for_status = MagicMock()
                r.json.return_value = responses[self._idx]
                self._idx += 1
                return r

        MockAsyncClient.side_effect = FakeClient

        result = await seed(test_db)
        assert result == 6

        row = await test_db.execute(text("SELECT COUNT(*) FROM users"))
        assert row.scalar_one() == 1
        row = await test_db.execute(text("SELECT COUNT(*) FROM posts"))
        assert row.scalar_one() == 1
        row = await test_db.execute(text("SELECT COUNT(*) FROM comments"))
        assert row.scalar_one() == 1
        row = await test_db.execute(text("SELECT COUNT(*) FROM albums"))
        assert row.scalar_one() == 1
        row = await test_db.execute(text("SELECT COUNT(*) FROM photos"))
        assert row.scalar_one() == 1
        row = await test_db.execute(text("SELECT COUNT(*) FROM todos"))
        assert row.scalar_one() == 1

    @patch("app.services.seed.httpx.AsyncClient")
    async def test_fetch_seed_payload_rejects_non_list(self, MockAsyncClient) -> None:
        class FakeClient:
            def __init__(self, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def get(self, url):
                r = MagicMock()
                r.raise_for_status = MagicMock()
                r.json.return_value = {"not": "a list"}
                return r

        MockAsyncClient.side_effect = FakeClient

        with pytest.raises(ValueError, match="Invalid users seed payload"):
            await fetch_seed_payload("http://seed.test")

    async def test_add_seed_rows_adds_all_resources(self, test_db) -> None:
        payload = {
            "users": [{"id": 1, "name": "A", "username": "a", "email": "a@b.com"}],
            "posts": [{"id": 1, "userId": 1, "title": "t", "body": "b"}],
            "comments": [{"id": 1, "postId": 1, "name": "c", "email": "c@x.com", "body": "cb"}],
            "albums": [{"id": 1, "userId": 1, "title": "al"}],
            "photos": [{"id": 1, "albumId": 1, "title": "ph", "url": "u", "thumbnailUrl": "tu"}],
            "todos": [{"id": 1, "userId": 1, "title": "td", "completed": True}],
        }

        add_seed_rows(test_db, payload)

        assert len(test_db.new) == 6
        assert {type(obj).__name__ for obj in test_db.new} == {
            "User",
            "Post",
            "Comment",
            "Album",
            "Photo",
            "Todo",
        }

    async def test_apply_seed_payload_respects_foreign_key_order(self) -> None:
        engine = create_async_engine(
            "sqlite+aiosqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        @sa_event.listens_for(engine.sync_engine, "connect")
        def _set_fk(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with session_factory() as session:
            payload = {
                "users": [{"id": 1, "name": "A", "username": "a", "email": "a@b.com"}],
                "posts": [{"id": 1, "userId": 1, "title": "t", "body": "b"}],
                "comments": [{"id": 1, "postId": 1, "name": "c", "email": "c@x.com", "body": "cb"}],
                "albums": [{"id": 1, "userId": 1, "title": "al"}],
                "photos": [
                    {"id": 1, "albumId": 1, "title": "ph", "url": "u", "thumbnailUrl": "tu"}
                ],
                "todos": [{"id": 1, "userId": 1, "title": "td", "completed": True}],
            }

            await apply_seed_payload(session, payload)

            for table, count in [
                ("users", 1),
                ("posts", 1),
                ("comments", 1),
                ("albums", 1),
                ("photos", 1),
                ("todos", 1),
            ]:
                row = await session.execute(text(f"SELECT COUNT(*) FROM {table}"))
                assert row.scalar_one() == count

        await engine.dispose()


class TestParseRuntimeSetting:
    def test_boolean_true(self) -> None:
        from app.services.runtime_settings import parse_runtime_setting

        assert parse_runtime_setting("RATE_LIMIT_ENABLED", True) == "true"

    def test_boolean_false(self) -> None:
        from app.services.runtime_settings import parse_runtime_setting

        assert parse_runtime_setting("RATE_LIMIT_ENABLED", False) == "false"

    def test_boolean_string_true(self) -> None:
        from app.services.runtime_settings import parse_runtime_setting

        assert parse_runtime_setting("RATE_LIMIT_ENABLED", "true") == "true"
        assert parse_runtime_setting("RATE_LIMIT_ENABLED", "TRUE") == "true"

    def test_boolean_string_false(self) -> None:
        from app.services.runtime_settings import parse_runtime_setting

        assert parse_runtime_setting("RATE_LIMIT_ENABLED", "false") == "false"
        assert parse_runtime_setting("RATE_LIMIT_ENABLED", "FALSE") == "false"

    def test_boolean_invalid(self) -> None:
        from app.services.runtime_settings import InvalidRuntimeSetting, parse_runtime_setting

        for val in ("yes", "no", "1", "0", 1, 0, "maybe"):
            try:
                parse_runtime_setting("RATE_LIMIT_ENABLED", val)
                raise AssertionError(f"Expected error for {val!r}")
            except InvalidRuntimeSetting as e:
                assert e.status_code == 400

    def test_rate_limit_max_valid(self) -> None:
        from app.services.runtime_settings import parse_runtime_setting

        assert parse_runtime_setting("RATE_LIMIT_MAX", 1) == "1"
        assert parse_runtime_setting("RATE_LIMIT_MAX", "1") == "1"
        assert parse_runtime_setting("RATE_LIMIT_MAX", 500) == "500"

    def test_rate_limit_max_min(self) -> None:
        from app.services.runtime_settings import InvalidRuntimeSetting, parse_runtime_setting

        try:
            parse_runtime_setting("RATE_LIMIT_MAX", 0)
            raise AssertionError("expected exception")
        except InvalidRuntimeSetting as e:
            assert e.status_code == 400

    def test_rate_limit_max_invalid_type(self) -> None:
        from app.services.runtime_settings import InvalidRuntimeSetting, parse_runtime_setting

        for val in ("abc", "12.5", "   "):
            try:
                parse_runtime_setting("RATE_LIMIT_MAX", val)
                raise AssertionError("expected exception")
            except InvalidRuntimeSetting as e:
                assert e.status_code == 400

    def test_rate_limit_window_ms_valid(self) -> None:
        from app.services.runtime_settings import parse_runtime_setting

        assert parse_runtime_setting("RATE_LIMIT_WINDOW_MS", 60000) == "60000"
        assert parse_runtime_setting("RATE_LIMIT_WINDOW_MS", "60000") == "60000"

    def test_rate_limit_window_ms_min(self) -> None:
        from app.services.runtime_settings import InvalidRuntimeSetting, parse_runtime_setting

        try:
            parse_runtime_setting("RATE_LIMIT_WINDOW_MS", 0)
            raise AssertionError("expected exception")
        except InvalidRuntimeSetting as e:
            assert e.status_code == 400

    def test_redis_port_valid(self) -> None:
        from app.services.runtime_settings import parse_runtime_setting

        assert parse_runtime_setting("REDIS_PORT", 1) == "1"
        assert parse_runtime_setting("REDIS_PORT", "6379") == "6379"
        assert parse_runtime_setting("REDIS_PORT", 65535) == "65535"

    def test_redis_port_invalid(self) -> None:
        from app.services.runtime_settings import InvalidRuntimeSetting, parse_runtime_setting

        for val in (0, 65536, -1, "abc"):
            try:
                parse_runtime_setting("REDIS_PORT", val)
                raise AssertionError("expected exception")
            except InvalidRuntimeSetting as e:
                assert e.status_code == 400

    def test_redis_db_valid(self) -> None:
        from app.services.runtime_settings import parse_runtime_setting

        assert parse_runtime_setting("REDIS_DB", 0) == "0"
        assert parse_runtime_setting("REDIS_DB", "0") == "0"
        assert parse_runtime_setting("REDIS_DB", 15) == "15"

    def test_redis_db_invalid(self) -> None:
        from app.services.runtime_settings import InvalidRuntimeSetting, parse_runtime_setting

        try:
            parse_runtime_setting("REDIS_DB", -1)
            raise AssertionError("expected exception")
        except InvalidRuntimeSetting as e:
            assert e.status_code == 400

    def test_string_key_valid(self) -> None:
        from app.services.runtime_settings import parse_runtime_setting

        assert parse_runtime_setting("REDIS_HOST", "localhost") == "localhost"
        assert (
            parse_runtime_setting("REDIS_URL", "redis://localhost:6379/0")
            == "redis://localhost:6379/0"
        )
        assert parse_runtime_setting("APP_ENV", "production") == "production"
        assert parse_runtime_setting("PORT", "8080") == "8080"
        assert parse_runtime_setting("DB_PATH", "/data/db.sqlite") == "/data/db.sqlite"
        assert parse_runtime_setting("DEFAULT_PAGE_SIZE", "25") == "25"

    def test_string_key_empty_rejected(self) -> None:
        from app.services.runtime_settings import InvalidRuntimeSetting, parse_runtime_setting

        try:
            parse_runtime_setting("REDIS_HOST", "")
            raise AssertionError("expected exception")
        except InvalidRuntimeSetting as e:
            assert e.status_code == 400

    def test_unknown_key_returns_404(self) -> None:
        from app.services.runtime_settings import InvalidRuntimeSetting, parse_runtime_setting

        try:
            parse_runtime_setting("NONEXISTENT_KEY", "value")
            raise AssertionError("expected exception")
        except InvalidRuntimeSetting as e:
            assert e.status_code == 404

    def test_dict_value_returns_400(self) -> None:
        from app.services.runtime_settings import InvalidRuntimeSetting, parse_runtime_setting

        try:
            parse_runtime_setting("PORT", {"foo": "bar"})
            raise AssertionError("expected exception")
        except InvalidRuntimeSetting as e:
            assert e.status_code == 400

    def test_list_value_returns_400(self) -> None:
        from app.services.runtime_settings import InvalidRuntimeSetting, parse_runtime_setting

        try:
            parse_runtime_setting("PORT", [1, 2, 3])
            raise AssertionError("expected exception")
        except InvalidRuntimeSetting as e:
            assert e.status_code == 400

    def test_null_value_returns_400(self) -> None:
        from app.services.runtime_settings import InvalidRuntimeSetting, parse_runtime_setting

        try:
            parse_runtime_setting("PORT", None)
            raise AssertionError("expected exception")
        except InvalidRuntimeSetting as e:
            assert e.status_code == 400

    def test_rate_limit_max_rejects_float(self) -> None:
        from app.services.runtime_settings import InvalidRuntimeSetting, parse_runtime_setting

        try:
            parse_runtime_setting("RATE_LIMIT_MAX", 1.5)
            raise AssertionError("expected exception")
        except InvalidRuntimeSetting as e:
            assert e.status_code == 400
            assert "integer" in e.detail

    def test_redis_port_rejects_float(self) -> None:
        from app.services.runtime_settings import InvalidRuntimeSetting, parse_runtime_setting

        try:
            parse_runtime_setting("REDIS_PORT", 1.5)
            raise AssertionError("expected exception")
        except InvalidRuntimeSetting as e:
            assert e.status_code == 400
            assert "integer" in e.detail

    def test_redis_db_rejects_float(self) -> None:
        from app.services.runtime_settings import InvalidRuntimeSetting, parse_runtime_setting

        try:
            parse_runtime_setting("REDIS_DB", 1.5)
            raise AssertionError("expected exception")
        except InvalidRuntimeSetting as e:
            assert e.status_code == 400
            assert "non-negative integer" in e.detail

    def test_redis_db_rejects_non_numeric_string(self) -> None:
        from app.services.runtime_settings import InvalidRuntimeSetting, parse_runtime_setting

        try:
            parse_runtime_setting("REDIS_DB", "abc")
            raise AssertionError("expected exception")
        except InvalidRuntimeSetting as e:
            assert e.status_code == 400
            assert "non-negative integer" in e.detail

    def test_rate_limit_values_extracts_only_rate_limit_keys(self) -> None:
        from app.models import Setting
        from app.services.runtime_settings import rate_limit_values

        rows = [
            Setting(key="RATE_LIMIT_ENABLED", value="true"),
            Setting(key="RATE_LIMIT_MAX", value="100"),
            Setting(key="RATE_LIMIT_WINDOW_MS", value="60000"),
            Setting(key="PORT", value="3000"),
            Setting(key="REDIS_HOST", value="localhost"),
        ]
        result = rate_limit_values(rows)
        assert result == {
            "RATE_LIMIT_ENABLED": "true",
            "RATE_LIMIT_MAX": "100",
            "RATE_LIMIT_WINDOW_MS": "60000",
        }

    def test_redis_values_extracts_only_redis_keys(self) -> None:
        from app.models import Setting
        from app.services.runtime_settings import redis_values

        rows = [
            Setting(key="REDIS_HOST", value="127.0.0.1"),
            Setting(key="REDIS_PORT", value="6379"),
            Setting(key="REDIS_DB", value="0"),
            Setting(key="REDIS_URL", value=""),
            Setting(key="RATE_LIMIT_MAX", value="100"),
        ]
        result = redis_values(rows)
        assert result == {
            "REDIS_HOST": "127.0.0.1",
            "REDIS_PORT": "6379",
            "REDIS_DB": "0",
            "REDIS_URL": "",
        }


class TestGetDb:
    async def test_get_db_yields_session(self) -> None:
        gen = get_db()
        session = await gen.__anext__()
        assert session is not None
        try:
            await gen.__anext__()
        except StopAsyncIteration:
            pass


class TestRuntimeSettings:
    async def test_seeded_defaults_can_be_loaded(self, test_db) -> None:
        config = Settings(_env_file=None)
        result = await seed_settings(test_db, config)
        assert result == 14
        loaded = await load_runtime_settings(test_db)
        assert loaded.rate_limit == {
            "RATE_LIMIT_ENABLED": "true",
            "RATE_LIMIT_MAX": "100",
            "RATE_LIMIT_WINDOW_MS": "60000",
        }
        assert loaded.redis["REDIS_HOST"] == "127.0.0.1"
        assert loaded.redis["REDIS_PORT"] == "6379"
        assert loaded.redis["REDIS_DB"] == "0"
        assert loaded.debug_sql is False

    async def test_debug_sql_true_loaded(self, test_db) -> None:
        config = Settings(_env_file=None, DEBUG_SQL=True)
        await seed_settings(test_db, config)
        loaded = await load_runtime_settings(test_db)
        assert loaded.debug_sql is True

    async def test_empty_redis_url_and_password_accepted(self, test_db) -> None:
        config = Settings(_env_file=None, REDIS_URL="", REDIS_PASSWORD="", ADMIN_KEY="")
        result = await seed_settings(test_db, config)
        assert result == 14
        loaded = await load_runtime_settings(test_db)
        assert loaded.redis.get("REDIS_URL") == ""
        assert loaded.redis.get("REDIS_PASSWORD") == ""

    async def test_empty_redis_host_rejected(self) -> None:
        from app.services.runtime_settings import InvalidRuntimeSetting, parse_runtime_setting

        with pytest.raises(InvalidRuntimeSetting, match="must not be empty"):
            parse_runtime_setting("REDIS_HOST", "")


class TestSettingsCache:
    async def test_default_page_size_cached_until_reset(self, test_db) -> None:
        from app.services.runtime_settings import default_page_size, reset_settings_cache

        test_db.add(Setting(key="DEFAULT_PAGE_SIZE", value="2", description=""))
        await test_db.commit()

        assert await default_page_size(test_db) == 2

        await test_db.execute(
            update(Setting).where(Setting.key == "DEFAULT_PAGE_SIZE").values(value="5")
        )
        await test_db.commit()

        assert await default_page_size(test_db) == 2

        reset_settings_cache()
        assert await default_page_size(test_db) == 5


class TestInitDb:
    async def test_init_db_completes(self) -> None:
        engine = create_async_engine("sqlite+aiosqlite://", echo=False)
        with patch("app.database.engine", engine):
            await init_db()


class TestDatabaseConfig:
    def test_enable_sqlite_foreign_keys_issues_pragma(self) -> None:
        from app.database import _enable_sqlite_foreign_keys

        cursor = MagicMock()
        connection = MagicMock()
        connection.cursor.return_value = cursor

        _enable_sqlite_foreign_keys(connection, None)

        cursor.execute.assert_called_once_with("PRAGMA foreign_keys=ON")
        cursor.close.assert_called_once()

    def test_foreign_keys_listener_registered_on_engine(self) -> None:
        from app.database import _enable_sqlite_foreign_keys, engine

        assert sa_event.contains(engine.sync_engine, "connect", _enable_sqlite_foreign_keys)
