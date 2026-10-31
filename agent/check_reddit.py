"""Explicit, opt-in read-only check; never prints tokens or secrets."""
import sys
from .config import RedditConfig
from .reddit import RedditError, check_connection

def main():
    try:
        check_connection(RedditConfig.from_env())
    except (ValueError, RedditError) as exc:
        print(f"Connection check failed: {exc}", file=sys.stderr)
        return 1
    print("Reddit app-only authentication and read-only request succeeded.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
