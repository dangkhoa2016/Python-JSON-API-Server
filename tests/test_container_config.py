import os
import subprocess
from pathlib import Path

import pytest

CONTAINER_NAME = "python-json-api-server-smoke"
VOLUME_NAME = "python-json-api-server-smoke-data"
NETWORK_NAME = "python-json-api-server-smoke-net"


@pytest.fixture
def fake_python_env(tmp_path: Path) -> tuple[dict[str, str], Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "invocations.log"
    fake_python = bin_dir / "python"
    fake_python.write_text(
        "#!/bin/sh\n"
        f'echo "python $*" >> "{log}"\n'
        'case "$*" in\n'
        '  *db_seed_startup*) exit "${SEED_STARTUP_EXIT:-0}" ;;\n'
        "  *) exit 0 ;;\n"
        "esac\n"
    )
    fake_python.chmod(0o755)
    final_marker = bin_dir / "final_marker"
    final_marker.write_text(f'#!/bin/sh\necho "final-command" >> "{log}"\n')
    final_marker.chmod(0o755)
    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
    env["SEED_BOOTSTRAP_LOG"] = str(log)
    return env, log


def run_entrypoint(
    env: dict[str, str],
    log: Path,
    extra_env: dict[str, str] | None = None,
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    run_env = dict(env)
    if extra_env:
        run_env.update(extra_env)
    result = subprocess.run(
        ["sh", "docker-entrypoint.sh", "final_marker"],
        capture_output=True,
        text=True,
        env=run_env,
    )
    invocations = log.read_text().splitlines() if log.exists() else []
    return result, invocations


def test_entrypoint_forwards_container_command():
    text = Path("docker-entrypoint.sh").read_text()
    assert 'exec "$@"' in text


def test_entrypoint_gates_remote_seed_behind_opt_in_flag():
    text = Path("docker-entrypoint.sh").read_text()
    assert "scripts.db_setup" not in text
    assert "scripts.db_migrate" in text
    assert "scripts.db_seed_settings" in text
    assert "scripts.db_seed_startup" in text
    assert "SEED_DATA_ON_STARTUP" in text


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "YES"])
def test_entrypoint_runs_startup_seed_for_true_spellings(
    fake_python_env: tuple[dict[str, str], Path], value: str
) -> None:
    env, log = fake_python_env
    result, invocations = run_entrypoint(env, log, {"SEED_DATA_ON_STARTUP": value})
    assert result.returncode == 0
    assert "python -m scripts.db_migrate" in invocations
    assert "python -m scripts.db_seed_settings" in invocations
    assert "python -m scripts.db_seed_startup" in invocations
    assert invocations.index("python -m scripts.db_seed_startup") > invocations.index(
        "python -m scripts.db_seed_settings"
    )
    assert invocations.index("python -m scripts.db_seed_startup") < invocations.index(
        "final-command"
    )


@pytest.mark.parametrize("value", ["0", "false", "FALSE", "no", "NO", ""])
def test_entrypoint_skips_startup_seed_for_false_spellings(
    fake_python_env: tuple[dict[str, str], Path], value: str
) -> None:
    env, log = fake_python_env
    result, invocations = run_entrypoint(env, log, {"SEED_DATA_ON_STARTUP": value})
    assert result.returncode == 0
    assert "python -m scripts.db_migrate" in invocations
    assert "python -m scripts.db_seed_settings" in invocations
    assert "python -m scripts.db_seed_startup" not in invocations
    assert "final-command" in invocations


def test_entrypoint_skips_startup_seed_when_unset(
    fake_python_env: tuple[dict[str, str], Path],
) -> None:
    env, log = fake_python_env
    result, invocations = run_entrypoint(env, log)
    assert result.returncode == 0
    assert "python -m scripts.db_migrate" in invocations
    assert "python -m scripts.db_seed_settings" in invocations
    assert "python -m scripts.db_seed_startup" not in invocations
    assert "final-command" in invocations


def test_entrypoint_rejects_invalid_seed_flag(fake_python_env: tuple[dict[str, str], Path]) -> None:
    env, log = fake_python_env
    result, invocations = run_entrypoint(env, log, {"SEED_DATA_ON_STARTUP": "maybe"})
    assert result.returncode == 2
    assert "Invalid SEED_DATA_ON_STARTUP value: expected true/false" in result.stderr
    assert "python -m scripts.db_seed_startup" not in invocations
    assert "final-command" not in invocations


def test_entrypoint_aborts_when_startup_seed_fails(
    fake_python_env: tuple[dict[str, str], Path],
) -> None:
    env, log = fake_python_env
    result, invocations = run_entrypoint(
        env, log, {"SEED_DATA_ON_STARTUP": "true", "SEED_STARTUP_EXIT": "1"}
    )
    assert result.returncode == 1
    assert "python -m scripts.db_seed_startup" in invocations
    assert "final-command" not in invocations


def test_dockerfile_is_multi_stage():
    text = Path("Dockerfile").read_text()
    assert "AS builder" in text
    assert text.count("FROM python:") == 2


def test_dockerfile_runs_as_non_root():
    text = Path("Dockerfile").read_text()
    assert "USER app" in text


def test_smoke_script_sets_eu():
    text = Path("scripts/container_smoke.sh").read_text()
    assert "set -eu" in text


def test_smoke_script_cleanup_trap():
    text = Path("scripts/container_smoke.sh").read_text()
    assert "trap cleanup EXIT" in text


def test_smoke_script_bounded_health_poll():
    text = Path("scripts/container_smoke.sh").read_text()
    assert "/health" in text
    assert "DEADLINE" in text
    assert "30" in text


def test_smoke_script_logs_on_failure():
    text = Path("scripts/container_smoke.sh").read_text()
    assert "docker logs" in text


def test_smoke_script_no_redis_enabled():
    text = Path("scripts/container_smoke.sh").read_text()
    assert "REDIS_ENABLED" not in text


def test_smoke_script_fresh_volume():
    text = Path("scripts/container_smoke.sh").read_text()
    assert "volume rm" in text


def test_smoke_script_cleanup_exact_names():
    text = Path("scripts/container_smoke.sh").read_text()
    assert CONTAINER_NAME in text
    assert VOLUME_NAME in text
    assert NETWORK_NAME in text
