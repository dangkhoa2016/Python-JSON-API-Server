import pytest

from app.config import Settings


def test_demo_seed_is_disabled_by_default() -> None:
    settings = Settings(_env_file=None)
    assert settings.SEED_DATA_ON_STARTUP is False


def test_demo_seed_timeout_defaults_to_sixty_seconds() -> None:
    settings = Settings(_env_file=None)
    assert settings.SEED_TIMEOUT_SECONDS == 60.0


def test_demo_seed_settings_can_be_overridden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEED_DATA_ON_STARTUP", "true")
    monkeypatch.setenv("SEED_TIMEOUT_SECONDS", "12.5")
    settings = Settings(_env_file=None)
    assert settings.SEED_DATA_ON_STARTUP is True
    assert settings.SEED_TIMEOUT_SECONDS == 12.5
