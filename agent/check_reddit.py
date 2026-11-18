"""Explicit, opt-in connection check via treg.to — never prints tokens or secrets."""
import sys

from .config import AppPaths
from . import secrets as _secrets
from .treg_reddit import TregError, TregRedditProvider


def main() -> int:
    try:
        paths = AppPaths.from_env()
        token = _secrets.get_treg_token(paths.data_dir)
        if not token:
            print("TREG_TOKEN is not configured. Set it via the dashboard or in .env.", file=sys.stderr)
            return 1
        TregRedditProvider(token).check_connection()
    except (ValueError, TregError) as exc:
        print(f"Connection check failed: {exc}", file=sys.stderr)
        return 1
    print("treg.to connection and Reddit data access succeeded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
