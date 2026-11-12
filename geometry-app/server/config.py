"""Server-only configuration; local edits are picked up without a restart."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def setting(name: str, default: str = '') -> str:
    if name in os.environ:
        return os.environ[name].strip()
    try:
        for line in (ROOT / '.env.local').read_text(encoding='utf-8-sig').splitlines():
            key, separator, value = line.strip().partition('=')
            if separator and key.strip() == name:
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
                return value
    except FileNotFoundError:
        pass
    return default
