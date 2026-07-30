from pathlib import Path


def update_env_file(env_path: Path, key: str, value: str) -> None:
    lines = env_path.read_text().splitlines() if env_path.exists() else []
    prefix = f"{key}="
    for i, line in enumerate(lines):
        if line.startswith(prefix):
            lines[i] = f"{prefix}{value}"
            break
    else:
        lines.append(f"{prefix}{value}")
    env_path.write_text("\n".join(lines) + "\n")
