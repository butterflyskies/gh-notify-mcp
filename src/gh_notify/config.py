"""Configuration from environment variables."""

from __future__ import annotations

import os
from pathlib import Path


def gh_config_dir() -> str:
    return os.environ.get("GH_CONFIG_DIR", str(Path.home() / ".config" / "gh"))


def gh_path() -> str:
    return os.environ.get("GH_NOTIFY_GH_PATH", "gh")


def db_dir() -> Path:
    p = Path(os.environ.get("GH_NOTIFY_DB_DIR", str(Path.home() / ".local" / "share" / "gh-notify")))
    p.mkdir(parents=True, exist_ok=True)
    return p


def db_path() -> Path:
    return db_dir() / "notifications.db"
