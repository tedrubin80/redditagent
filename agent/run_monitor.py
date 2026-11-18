"""Explicit, opt-in read-only poll via treg.to. Does not post or start a background daemon."""
from __future__ import annotations

import sys

from .config import AppPaths
from . import secrets as _secrets
from .monitor import poll_once
from .settings import MonitorSettings
from .store import Store
from .treg_reddit import TregError, TregRedditProvider


def main() -> int:
    try:
        paths = AppPaths.from_env()
        token = _secrets.get_treg_token(paths.data_dir)
        if not token:
            print("TREG_TOKEN is not configured. Set it via the dashboard or in .env.", file=sys.stderr)
            return 1
        settings = MonitorSettings.load(paths.settings_path)
        store = Store(paths.db_path)
        provider = TregRedditProvider(token)
        result = poll_once(provider, settings, store)
    except (ValueError, TregError) as exc:
        print(f"Monitor poll failed: {exc}", file=sys.stderr)
        return 1
    print(result.message)
    return 1 if result.error else 0


if __name__ == "__main__":
    sys.exit(main())
