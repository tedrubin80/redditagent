"""Explicit, opt-in read-only poll. Does not post or start a background daemon."""
from __future__ import annotations

import sys

from .config import AppPaths, RedditConfig
from .monitor import poll_once
from .reddit import OAuthRedditProvider, RedditError
from .settings import MonitorSettings
from .store import Store


def main() -> int:
    try:
        paths = AppPaths.from_env()
        settings = MonitorSettings.load(paths.settings_path)
        store = Store(paths.db_path)
        provider = OAuthRedditProvider(RedditConfig.from_env())
        result = poll_once(provider, settings, store)
    except (ValueError, RedditError) as exc:
        print(f"Monitor poll failed: {exc}", file=sys.stderr)
        return 1
    print(result.message)
    return 1 if result.error else 0


if __name__ == "__main__":
    sys.exit(main())
