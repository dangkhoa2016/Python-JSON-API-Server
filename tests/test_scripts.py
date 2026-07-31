"""Validate developer scripts and dependency contracts."""

import asyncio
import re
import subprocess
import tomllib
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest


def test_all_run_script_commands_have_declared_dependencies() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text())
    dev = "\n".join(pyproject["project"]["optional-dependencies"]["dev"])
    script = Path("scripts/run.sh").read_text()
    if "pytest-watch" in script:
        assert "pytest-watch" in dev


def test_run_script_module_targets_exist() -> None:
    script = Path("scripts/run.sh").read_text()
    missing = [
        name
        for name in re.findall(r"python -m scripts\.([a-z_]+)", script)
        if not Path("scripts", f"{name}.py").exists()
    ]
    assert missing == []


def test_shell_scripts_have_valid_syntax() -> None:
    subprocess.run(["bash", "-n", "scripts/run.sh"], check=True)
    subprocess.run(["sh", "-n", "docker-entrypoint.sh"], check=True)


class TestDbSeedStartup:
    async def test_seed_for_startup_initializes_db_before_session(self) -> None:
        from scripts import db_seed_startup

        order: list[str] = []

        async def fake_init_db() -> None:
            order.append("init_db")

        async def fake_seed(db: Any) -> int:
            order.append("seed")
            return 42

        session = object()

        class FakeSession:
            async def __aenter__(self) -> object:
                order.append("session")
                return session

            async def __aexit__(self, *args: Any) -> None:
                pass

        with (
            patch.object(db_seed_startup, "init_db", side_effect=fake_init_db),
            patch.object(db_seed_startup, "seed", side_effect=fake_seed),
            patch.object(db_seed_startup, "async_session", return_value=FakeSession()),
        ):
            count = await db_seed_startup.seed_for_startup(5.0)

        assert count == 42
        assert order == ["init_db", "session", "seed"]

    def test_seed_service_is_reused(self) -> None:
        from app.services import seed as seed_service
        from scripts import db_seed_startup

        assert db_seed_startup.seed is seed_service.seed

    async def test_slow_seed_raises_timeout_error(self) -> None:
        from scripts import db_seed_startup

        async def slow_seed(db: Any) -> int:
            await asyncio.sleep(10)
            return 0

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=object())
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.object(db_seed_startup, "init_db", new_callable=AsyncMock),
            patch.object(db_seed_startup, "seed", side_effect=slow_seed),
            patch.object(db_seed_startup, "async_session", return_value=mock_cm),
        ):
            with pytest.raises(TimeoutError):
                await db_seed_startup.seed_for_startup(0.01)

    async def test_non_positive_timeout_rejected_before_db_work(self) -> None:
        from scripts import db_seed_startup

        with patch.object(db_seed_startup, "init_db", new_callable=AsyncMock) as init_db_mock:
            with pytest.raises(ValueError, match="must be positive"):
                await db_seed_startup.seed_for_startup(0)
            with pytest.raises(ValueError, match="must be positive"):
                await db_seed_startup.seed_for_startup(-1.0)
        init_db_mock.assert_not_called()

    def test_main_returns_zero_and_prints_count(self, capsys: pytest.CaptureFixture[str]) -> None:
        from scripts import db_seed_startup

        with (
            patch.object(db_seed_startup, "settings") as mock_settings,
            patch.object(
                db_seed_startup, "seed_for_startup", new_callable=AsyncMock, return_value=57
            ),
        ):
            mock_settings.SEED_TIMEOUT_SECONDS = 60.0
            result = db_seed_startup.main()
        captured = capsys.readouterr()
        assert result == 0
        assert "57" in captured.out

    def test_main_returns_one_on_timeout(self, capsys: pytest.CaptureFixture[str]) -> None:
        from scripts import db_seed_startup

        with (
            patch.object(db_seed_startup, "settings") as mock_settings,
            patch.object(
                db_seed_startup,
                "seed_for_startup",
                new_callable=AsyncMock,
                side_effect=TimeoutError,
            ),
        ):
            mock_settings.SEED_TIMEOUT_SECONDS = 60.0
            result = db_seed_startup.main()
        captured = capsys.readouterr()
        assert result == 1
        assert "timed out" in captured.err
        assert captured.out == ""

    def test_main_sanitizes_failures(self, capsys: pytest.CaptureFixture[str]) -> None:
        from scripts import db_seed_startup

        secret = "postgres://user:secret@db.example.com:5432/demo"
        with (
            patch.object(db_seed_startup, "settings") as mock_settings,
            patch.object(
                db_seed_startup,
                "seed_for_startup",
                new_callable=AsyncMock,
                side_effect=RuntimeError(secret),
            ),
        ):
            mock_settings.SEED_TIMEOUT_SECONDS = 60.0
            result = db_seed_startup.main()
        captured = capsys.readouterr()
        assert result == 1
        assert "failed" in captured.err
        assert secret not in captured.err
        assert "Traceback" not in captured.err

    def test_module_exits_via_system_exit(self) -> None:
        text = Path("scripts/db_seed_startup.py").read_text()
        assert text.rstrip().endswith("raise SystemExit(main())")
