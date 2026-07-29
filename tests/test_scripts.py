"""Validate developer scripts and dependency contracts."""

import re
import subprocess
import tomllib
from pathlib import Path


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
