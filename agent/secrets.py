"""Persistent credential store written to data/secrets.json.

Priority: environment variables always win over the file.  The file is the
fallback for headless installs where editing .env is inconvenient — the
dashboard writes to it and the server reads from it on every request so
changes take effect immediately without a restart.

The file is kept under DATA_DIR (the same Docker volume as the SQLite DB and
settings), so it survives container rebuilds.  It is never committed to git
(secrets.json is in .gitignore).
"""
from __future__ import annotations

import json
import os
from pathlib import Path


_FILENAME = "secrets.json"


def _secrets_path(data_dir: Path) -> Path:
    return data_dir / _FILENAME


def load(data_dir: Path) -> dict:
    path = _secrets_path(data_dir)
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save(data_dir: Path, updates: dict) -> None:
    path = _secrets_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = load(data_dir)
    merged = {**existing, **{k: v for k, v in updates.items() if v is not None}}
    # Tombstone: a value of "" removes the key.
    merged = {k: v for k, v in merged.items() if v != ""}
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def get_treg_token(data_dir: Path) -> str:
    """Return TREG_TOKEN from env first, then secrets file."""
    env_val = os.environ.get("TREG_TOKEN", "").strip()
    if env_val:
        return env_val
    return load(data_dir).get("treg_token", "")


def get_dashboard_creds(data_dir: Path) -> tuple[str, str] | None:
    """Return (user, password) from env first, then secrets file. None if unset."""
    env_user = os.environ.get("DASHBOARD_USER", "").strip()
    env_pass = os.environ.get("DASHBOARD_PASSWORD", "").strip()
    if env_user and env_pass:
        return env_user, env_pass
    s = load(data_dir)
    user = s.get("dashboard_user", "")
    password = s.get("dashboard_password", "")
    if user and password:
        return user, password
    return None
