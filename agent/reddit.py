"""Reddit provider interface and app-only OAuth implementation (read-only)."""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .rate_limit import RateLimiter, backoff_seconds


class RedditError(Exception):
    pass


@dataclass(frozen=True)
class RedditPost:
    fullname: str
    subreddit: str
    title: str
    selftext: str
    url: str
    permalink: str
    author: str
    created_utc: float
    removed: bool = False


class RedditProvider(Protocol):
    def check_connection(self) -> bool: ...
    def list_new_posts(self, subreddit: str, limit: int = 25) -> list[RedditPost]: ...
    def fetch_posts_by_fullname(self, fullnames: list[str]) -> list[RedditPost]: ...


class OAuthRedditProvider:
    """App-only (client credentials) Reddit adapter. No posting, no user identity."""

    token_url = "https://www.reddit.com/api/v1/access_token"
    api_base = "https://oauth.reddit.com"

    def __init__(self, config, limiter: RateLimiter | None = None):
        self._config = config
        self._limiter = limiter or RateLimiter()
        self._token: str | None = None

    def check_connection(self) -> bool:
        token = self._ensure_token()
        # App-only tokens have no user identity. Use an application-readable endpoint instead.
        result = self._request_json(
            Request(
                f"{self.api_base}/api/v1/scopes",
                headers=self._auth_headers(token),
            )
        )
        if not isinstance(result, dict) or not result:
            raise RedditError("Reddit returned an unexpected scopes response.")
        return True

    def list_new_posts(self, subreddit: str, limit: int = 25) -> list[RedditPost]:
        name = subreddit.strip().lstrip("r/").lower()
        if not name:
            raise RedditError("Subreddit name is required.")
        limit = max(1, min(100, int(limit)))
        payload = self._oauth_get(f"/r/{name}/new", {"limit": str(limit), "raw_json": "1"})
        children = (((payload or {}).get("data") or {}).get("children")) or []
        posts: list[RedditPost] = []
        for child in children:
            if not isinstance(child, dict):
                continue
            data = child.get("data") or {}
            post = _post_from_listing(data)
            if post:
                posts.append(post)
        return posts

    def fetch_posts_by_fullname(self, fullnames: list[str]) -> list[RedditPost]:
        if not fullnames:
            return []
        # Reddit /api/info accepts comma-separated fullnames.
        payload = self._oauth_get("/api/info", {"id": ",".join(fullnames), "raw_json": "1"})
        children = (((payload or {}).get("data") or {}).get("children")) or []
        posts: list[RedditPost] = []
        seen = set()
        for child in children:
            if not isinstance(child, dict):
                continue
            data = child.get("data") or {}
            post = _post_from_listing(data)
            if post:
                posts.append(post)
                seen.add(post.fullname)
        # Fullnames absent from the response are treated as removed/unavailable.
        for fullname in fullnames:
            if fullname not in seen:
                posts.append(
                    RedditPost(
                        fullname=fullname,
                        subreddit="",
                        title="",
                        selftext="",
                        url="",
                        permalink="",
                        author="[deleted]",
                        created_utc=0.0,
                        removed=True,
                    )
                )
        return posts

    def _ensure_token(self) -> str:
        if self._token:
            return self._token
        basic = base64.b64encode(
            f"{self._config.client_id}:{self._config.client_secret}".encode()
        ).decode()
        request = Request(
            self.token_url,
            data=urlencode({"grant_type": "client_credentials"}).encode(),
            headers={
                "Authorization": "Basic " + basic,
                "User-Agent": self._config.user_agent,
            },
            method="POST",
        )
        token = self._request_json(request).get("access_token")
        if not isinstance(token, str) or not token:
            raise RedditError(
                "Reddit did not issue an app-only token; check the app type and credentials."
            )
        self._token = token
        return token

    def _oauth_get(self, path: str, params: dict[str, str]) -> dict:
        query = urlencode(params)
        url = f"{self.api_base}{path}?{query}"
        for attempt in range(5):
            token = self._ensure_token()
            self._limiter.wait_turn()
            request = Request(url, headers=self._auth_headers(token))
            try:
                return self._request_json(request)
            except RedditError as exc:
                message = str(exc)
                if "HTTP 401" in message:
                    self._token = None
                    continue
                if "HTTP 429" in message:
                    import time

                    time.sleep(backoff_seconds(attempt))
                    continue
                raise
        raise RedditError("Reddit request failed after retries.")

    def _auth_headers(self, token: str) -> dict[str, str]:
        return {
            "Authorization": "Bearer " + token,
            "User-Agent": self._config.user_agent,
        }

    def _request_json(self, request: Request) -> dict:
        try:
            with urlopen(request, timeout=15) as response:
                return json.load(response)
        except HTTPError as exc:
            raise RedditError(
                f"Reddit returned HTTP {exc.code}; check app type, credentials, and access."
            ) from None
        except (URLError, TimeoutError, OSError):
            raise RedditError("Could not reach Reddit. Check your network and try again.") from None
        except (ValueError, UnicodeDecodeError):
            raise RedditError("Reddit returned an invalid response.") from None


def _post_from_listing(data: dict) -> RedditPost | None:
    if not isinstance(data, dict):
        return None
    name = data.get("name")
    if not isinstance(name, str) or not name.startswith("t3_"):
        return None
    title = str(data.get("title") or "")
    selftext = str(data.get("selftext") or "")
    author = str(data.get("author") or "[deleted]")
    subreddit = str(data.get("subreddit") or "").lower()
    permalink = str(data.get("permalink") or "")
    url = str(data.get("url") or "")
    if permalink.startswith("/"):
        permalink_url = "https://www.reddit.com" + permalink
    else:
        permalink_url = permalink or url
    removed = bool(
        data.get("removed_by_category")
        or selftext in {"[removed]", "[deleted]"}
        or author == "[deleted]" and selftext in {"", "[removed]", "[deleted]"}
    )
    try:
        created = float(data.get("created_utc") or 0)
    except (TypeError, ValueError):
        created = 0.0
    return RedditPost(
        fullname=name,
        subreddit=subreddit,
        title=title,
        selftext=selftext,
        url=permalink_url,
        permalink=permalink,
        author=author,
        created_utc=created,
        removed=removed,
    )


def check_connection(config) -> bool:
    """Backward-compatible helper used by the foundation connection check."""
    return OAuthRedditProvider(config).check_connection()
