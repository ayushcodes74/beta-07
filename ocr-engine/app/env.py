"""Load ``ocr-engine/.env`` into ``os.environ`` (no python-dotenv dependency).

Existing environment variables always win, so deployments and tests can override any value.
"""

import os
from pathlib import Path

_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
_loaded = False


def load_env_file(path: Path = _ENV_FILE) -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if key:
            os.environ.setdefault(key, value)
