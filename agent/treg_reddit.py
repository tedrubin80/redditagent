"""Reddit provider backed by treg.to — no Reddit OAuth required.

Calls treg's proxy to Crawl4AI and TikHub endpoints.  Set TREG_TOKEN (a team
agent token or dashboard API key from https://treg.to) to run the agent.

Pricing (treg metered from your prepaid balance):
  - list_new_posts / search_posts : crawl4ai.reddit.subreddit.posts or
                                    crawl4ai.reddit.search.posts  → $0.0009/call
  - fetch_posts_by_fullname       : tikhub.x.reddit-app-fetch-post-details-batch
                                    (≤5 fullnames per call)        → $0.005/call
  - fetch_comments                : crawl4ai.reddit.post.comments  → $0.0009/call
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .reddit import RedditPost, RedditProvider


TREG_BASE = "https://treg.to/call"
_CRAWL4AI_SUBREDDIT = "crawl4ai.reddit.subreddit.posts"
_CRAWL4AI_SEARCH = "crawl4ai.reddit.search.posts"
_CRAWL4AI_COMMENTS = "crawl4ai.reddit.post.comments"
_TIKHUB_BATCH = "tikhub.x.reddit-app-fetch-post-details-batch"
_TIKHUB_SINGLE = "tikhub.x.reddit-app-fetch-post-details"

# TikHub batch accepts ≤5 fullnames per call.
_TIKHUB_BATCH_SIZE = 5


class TregError(Exception):
    pass


class TregRedditProvider:
    """RedditProvider that proxies through treg.to — no Reddit credentials needed."""

    def __init__(self, token: str, timeout: int = 20):
        if not token:
            raise ValueError("TREG_TOKEN is required for TregRedditProvider")
        self._token = token
        self._timeout = timeout

    # ------------------------------------------------------------------
    # RedditProvider protocol
    # ------------------------------------------------------------------

    def check_connection(self) -> bool:
        """Verify the treg token works by fetching a minimal subreddit page."""
        result = self._post(_CRAWL4AI_SUBREDDIT, {"subreddit": "announcements", "limit": 1})
        rows = result.get("rows") or []
        if not isinstance(rows, list):
            raise TregError("Unexpected response from treg subreddit endpoint.")
        return True

    def list_new_posts(self, subreddit: str, limit: int = 25) -> list[RedditPost]:
        name = _strip_r_prefix(subreddit)
        if not name:
            raise TregError("Subreddit name is required.")
        limit = max(1, min(250, int(limit)))
        result = self._post(_CRAWL4AI_SUBREDDIT, {"subreddit": name, "sort": "new", "limit": limit})
        return _parse_crawl4ai_rows(result, subreddit_hint=name)

    def fetch_posts_by_fullname(self, fullnames: list[str]) -> list[RedditPost]:
        """Look up posts by t3_ fullname in batches of up to 5 (TikHub limit)."""
        if not fullnames:
            return []
        posts: list[RedditPost] = []
        seen: set[str] = set()
        for i in range(0, len(fullnames), _TIKHUB_BATCH_SIZE):
            chunk = fullnames[i : i + _TIKHUB_BATCH_SIZE]
            chunk_posts = self._fetch_tikhub_batch(chunk)
            for p in chunk_posts:
                posts.append(p)
                seen.add(p.fullname)
        # Fullnames absent from all responses are treated as removed.
        for fullname in fullnames:
            if fullname not in seen:
                posts.append(_deleted_post(fullname))
        return posts

    # ------------------------------------------------------------------
    # Extended capabilities (not in RedditProvider protocol)
    # ------------------------------------------------------------------

    def search_posts(
        self,
        query: str,
        subreddit: str | None = None,
        limit: int = 25,
        sort: str = "relevance",
        timeframe: str = "all",
    ) -> list[RedditPost]:
        """Search Reddit posts by keyword across all subreddits (or one)."""
        if not query.strip():
            raise TregError("Search query is required.")
        limit = max(1, min(250, int(limit)))
        body: dict[str, Any] = {"query": query.strip(), "sort": sort, "t": timeframe, "limit": limit}
        if subreddit:
            body["subreddit"] = _strip_r_prefix(subreddit)
        result = self._post(_CRAWL4AI_SEARCH, body)
        return _parse_crawl4ai_rows(result, subreddit_hint=subreddit or "")

    def fetch_comments(
        self,
        post_url: str,
        limit: int = 100,
        sort: str = "top",
    ) -> list[dict]:
        """Fetch comments for a post URL. Returns a list of comment dicts."""
        result = self._post(_CRAWL4AI_COMMENTS, {"url": post_url, "limit": limit, "sort": sort})
        rows = result.get("rows") or []
        return [
            {
                "author": str(r.get("author") or "[deleted]"),
                "text": str(r.get("text") or ""),
                "score": r.get("score"),
                "depth": int(r.get("depth") or 0),
                "created": str(r.get("created") or ""),
                "url": str(r.get("url") or ""),
                "id": str(r.get("id") or ""),
            }
            for r in rows
            if isinstance(r, dict)
        ]

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "X-Treg-Token": self._token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _post(self, endpoint_id: str, body: dict) -> dict:
        url = f"{TREG_BASE}/{endpoint_id}"
        data = json.dumps(body).encode("utf-8")
        request = Request(url, data=data, headers=self._headers(), method="POST")
        return self._do_request(request, endpoint_id)

    def _get(self, endpoint_id: str, params: dict) -> dict:
        qs = urlencode(params)
        url = f"{TREG_BASE}/{endpoint_id}?{qs}"
        headers = {k: v for k, v in self._headers().items() if k != "Content-Type"}
        request = Request(url, headers=headers, method="GET")
        return self._do_request(request, endpoint_id)

    def _do_request(self, request: Request, endpoint_id: str) -> dict:
        try:
            with urlopen(request, timeout=self._timeout) as resp:
                raw = resp.read()
                try:
                    return json.loads(raw)
                except (ValueError, UnicodeDecodeError):
                    raise TregError(f"treg/{endpoint_id}: invalid JSON response")
        except HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="replace")[:300]
            except Exception:
                pass
            raise TregError(
                f"treg/{endpoint_id}: HTTP {exc.code}" + (f" — {body}" if body else "")
            ) from None
        except (URLError, TimeoutError, OSError) as exc:
            raise TregError(f"treg/{endpoint_id}: network error — {exc}") from None

    def _fetch_tikhub_batch(self, fullnames: list[str]) -> list[RedditPost]:
        """Call TikHub batch endpoint for ≤5 fullnames; falls back to single if batch fails."""
        if not fullnames:
            return []
        try:
            result = self._get(
                _TIKHUB_BATCH,
                {
                    "post_ids": ",".join(fullnames),
                    "include_comment_id": "false",
                    "need_format": "false",
                },
            )
            items = (result.get("data") or {}).get("postsInfoByIds") or []
            if isinstance(items, list) and items:
                return [
                    _tikhub_item_to_post(item)
                    for item in items
                    if isinstance(item, dict)
                ]
        except TregError:
            pass

        # Fallback: fetch each one individually.
        posts = []
        for fullname in fullnames:
            try:
                result = self._get(
                    _TIKHUB_SINGLE,
                    {"post_id": fullname, "include_comment_id": "false", "need_format": "false"},
                )
                items = (result.get("data") or {}).get("postsInfoByIds") or []
                if isinstance(items, list) and items:
                    item = items[0]
                    if isinstance(item, dict):
                        posts.append(_tikhub_item_to_post(item, fallback_fullname=fullname))
                        continue
            except TregError:
                pass
            posts.append(_deleted_post(fullname))
        return posts


# ------------------------------------------------------------------
# Response parsers
# ------------------------------------------------------------------

def _parse_crawl4ai_rows(result: dict, subreddit_hint: str = "") -> list[RedditPost]:
    rows = result.get("rows") or []
    posts = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        post = _crawl4ai_row_to_post(row, subreddit_hint)
        if post:
            posts.append(post)
    return posts


def _crawl4ai_row_to_post(row: dict, subreddit_hint: str = "") -> RedditPost | None:
    """Map a crawl4ai reddit row to a RedditPost.

    crawl4ai columns: id, title, url (permalink), link (target), score,
    comments, author, created (ISO-8601), flair, subreddit, text.
    """
    post_id = str(row.get("id") or "").strip()
    if not post_id:
        return None
    fullname = f"t3_{post_id}"
    title = str(row.get("title") or "")
    # crawl4ai: "url" is the reddit permalink; "link" is the external link.
    permalink_url = str(row.get("url") or "")
    author = str(row.get("author") or "[deleted]")
    subreddit = _strip_r_prefix(str(row.get("subreddit") or subreddit_hint))
    selftext = str(row.get("text") or "")
    created = _parse_iso_or_float(row.get("created"), 0.0)
    return RedditPost(
        fullname=fullname,
        subreddit=subreddit,
        title=title,
        selftext=selftext,
        url=permalink_url,
        permalink=permalink_url,
        author=author,
        created_utc=created,
        removed=False,
    )


def _tikhub_item_to_post(item: dict, fallback_fullname: str = "") -> RedditPost:
    """Map a TikHub postsInfoByIds item to a RedditPost.

    TikHub returns Reddit's internal GraphQL format.  Field names vary between
    the formatted and raw response modes, so we try several candidate keys.
    """
    # Fullname / id
    raw_id = str(item.get("id") or item.get("name") or fallback_fullname or "")
    if raw_id.startswith("t3_"):
        fullname = raw_id
    elif raw_id:
        fullname = f"t3_{raw_id}"
    else:
        fullname = fallback_fullname

    title = str(item.get("title") or "")

    # Author: GraphQL returns {"name": "..."} or a plain string.
    author_raw = item.get("author") or item.get("authorName") or "[deleted]"
    author = str(author_raw.get("name") if isinstance(author_raw, dict) else author_raw)

    # Subreddit
    sub_raw = item.get("subreddit") or item.get("subredditName") or ""
    subreddit = _strip_r_prefix(str(sub_raw.get("name") if isinstance(sub_raw, dict) else sub_raw))

    selftext = str(
        item.get("selftext") or item.get("body") or item.get("bodyText") or ""
    )
    permalink = str(item.get("permalink") or "")
    if permalink.startswith("/"):
        url = "https://www.reddit.com" + permalink
    else:
        url = permalink or str(item.get("url") or "")

    created_raw = item.get("created") or item.get("createdAt") or item.get("created_utc") or 0
    created = _parse_iso_or_float(created_raw, 0.0)

    removed = bool(
        item.get("isRemoved")
        or item.get("removed")
        or item.get("removedByCategory")
        or selftext in {"[removed]", "[deleted]"}
        or (author in {"[deleted]"} and selftext in {"", "[removed]", "[deleted]"})
    )

    return RedditPost(
        fullname=fullname,
        subreddit=subreddit,
        title=title,
        selftext=selftext,
        url=url,
        permalink=permalink,
        author=author,
        created_utc=created,
        removed=removed,
    )


def _strip_r_prefix(name: str) -> str:
    """Normalize a subreddit name: lowercase, strip the r/ prefix if present."""
    name = name.lower().strip()
    if name.startswith("r/"):
        name = name[2:]
    return name


def _deleted_post(fullname: str) -> RedditPost:
    return RedditPost(
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


def _parse_iso_or_float(value: Any, default: float) -> float:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return default
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            pass
        try:
            return float(value)
        except ValueError:
            return default
    return default
