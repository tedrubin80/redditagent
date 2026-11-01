"""Configuration parsing without exposing credentials in representations."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class RedditConfig:
    client_id: str = field(repr=False)
    client_secret: str = field(repr=False)
    user_agent: str

    @classmethod
    def from_env(cls) -> "RedditConfig":
        names = ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT")
        values = [os.environ.get(name, "").strip() for name in names]
        missing = [name for name, value in zip(names, values) if not value]
        if missing:
            raise ValueError("Missing configuration: " + ", ".join(missing))
        if "REPLACE_ME" in values[2]:
            raise ValueError("Set REDDIT_USER_AGENT to a descriptive identifier and your username")
        return cls(*values)


@dataclass(frozen=True)
class AppPaths:
    data_dir: Path
    settings_path: Path
    db_path: Path

    @classmethod
    def from_env(cls) -> "AppPaths":
        data_dir = Path(os.environ.get("DATA_DIR", "data")).expanduser()
        settings = os.environ.get("SETTINGS_PATH", "").strip()
        settings_path = Path(settings).expanduser() if settings else data_dir / "settings.json"
        db = os.environ.get("DB_PATH", "").strip()
        db_path = Path(db).expanduser() if db else data_dir / "agent.db"
        return cls(data_dir=data_dir, settings_path=settings_path, db_path=db_path)
