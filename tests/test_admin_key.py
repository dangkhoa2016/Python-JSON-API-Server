from __future__ import annotations

from pathlib import Path

from argon2 import PasswordHasher
from sqlalchemy import select, text

from app.models import Setting
from app.services.env_file import update_env_file
from app.services.seed_settings import set_admin_key


class TestUpdateEnvFile:
    def test_replaces_existing_line(self, tmp_path: Path) -> None:
        p = tmp_path / ".env"
        p.write_text("# comment\nADMIN_KEY=old-value\nPORT=3000\n")

        update_env_file(p, "ADMIN_KEY", "new-value")

        assert p.read_text() == "# comment\nADMIN_KEY=new-value\nPORT=3000\n"

    def test_appends_when_line_missing(self, tmp_path: Path) -> None:
        p = tmp_path / ".env"
        p.write_text("# comment\nPORT=3000\n")

        update_env_file(p, "ADMIN_KEY", "new-value")

        assert p.read_text() == "# comment\nPORT=3000\nADMIN_KEY=new-value\n"

    def test_creates_file_when_missing(self, tmp_path: Path) -> None:
        p = tmp_path / ".env"

        update_env_file(p, "ADMIN_KEY", "new-value")

        assert p.read_text() == "ADMIN_KEY=new-value\n"


class TestSetAdminKey:
    async def test_creates_row_when_missing(self, test_db) -> None:
        await test_db.execute(text("DELETE FROM settings"))
        await test_db.commit()

        row = await set_admin_key(test_db, "super-secret-value")

        assert row.key == "ADMIN_KEY"
        result = await test_db.execute(select(Setting).where(Setting.key == "ADMIN_KEY"))
        saved = result.scalar_one()
        assert PasswordHasher().verify(saved.value, "super-secret-value")

    async def test_updates_existing_row(self, test_db) -> None:
        await test_db.execute(text("DELETE FROM settings"))
        await test_db.commit()
        await set_admin_key(test_db, "first-secret-value")
        result = await test_db.execute(select(Setting).where(Setting.key == "ADMIN_KEY"))
        first_hash = result.scalar_one().value

        row = await set_admin_key(test_db, "second-secret-value")

        assert row.value != first_hash
        result = await test_db.execute(select(Setting).where(Setting.key == "ADMIN_KEY"))
        saved = result.scalar_one()
        assert saved.value != first_hash
        assert PasswordHasher().verify(saved.value, "second-secret-value")


class TestReadSecret:
    def test_prompts_when_argument_missing(self, monkeypatch) -> None:
        from scripts import set_admin_key

        monkeypatch.setattr(set_admin_key.getpass, "getpass", lambda prompt: "prompt-secret")
        assert set_admin_key.read_secret(None) == "prompt-secret"

    def test_uses_explicit_argument(self) -> None:
        from scripts.set_admin_key import read_secret

        assert read_secret("automation-secret") == "automation-secret"


class TestValidateSecret:
    def test_empty_rejected(self) -> None:
        from scripts.set_admin_key import validate_secret

        assert validate_secret("") is not None

    def test_whitespace_rejected(self) -> None:
        from scripts.set_admin_key import validate_secret

        assert validate_secret("my secret") is not None
        assert validate_secret("my\tsecret") is not None

    def test_valid_secret_accepted(self) -> None:
        from scripts.set_admin_key import validate_secret

        assert validate_secret("super-secret-value") is None


class TestSecretWarning:
    def test_short_key_warns(self) -> None:
        from scripts.set_admin_key import secret_warning

        assert secret_warning("short") is not None

    def test_long_enough_key_no_warning(self) -> None:
        from scripts.set_admin_key import secret_warning

        assert secret_warning("a-very-long-secret") is None
