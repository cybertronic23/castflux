import os
from pathlib import Path


def configured_secret(value: str | None) -> bool:
    if not value:
        return False
    value = value.strip()
    if not value:
        return False
    placeholders = ("你的", "your_", "your-", "sk-...", "hf_...")
    return not any(marker in value.lower() for marker in placeholders)


def app_root() -> Path:
    return Path(__file__).resolve().parents[2]


def env_paths(include_home: bool = False) -> list[Path]:
    paths = [Path.cwd() / ".env", app_root() / ".env"]
    if include_home:
        paths.append(Path.home() / ".env")

    unique = []
    seen = set()
    for path in paths:
        resolved = path.resolve()
        if resolved not in seen:
            unique.append(path)
            seen.add(resolved)
    return unique


def read_env_file(path: str | Path) -> dict[str, str]:
    path = Path(path)
    values = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def read_env_files(include_home: bool = False) -> dict[str, str]:
    values = {}
    for path in env_paths(include_home=include_home):
        values.update(read_env_file(path))
    return values


def load_env_files(include_home: bool = False, override: bool = False) -> dict[str, str]:
    loaded = read_env_files(include_home=include_home)
    for key, value in loaded.items():
        if override:
            os.environ[key] = value
        else:
            os.environ.setdefault(key, value)
    return loaded
