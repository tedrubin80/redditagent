"""Read-only poll cycle: fetch → filter → store → reconcile deletions."""
from __future__ import annotations

from dataclasses import dataclass

from .matching import evaluate_post
from .reddit import RedditError, RedditProvider
from .settings import MonitorSettings
from .store import Store


@dataclass(frozen=True)
class PollResult:
    scanned: int
    inserted: int
    deleted: int
    paused: bool
    message: str
    error: str | None = None


def poll_once(provider: RedditProvider, settings: MonitorSettings, store: Store) -> PollResult:
    if store.get_paused():
        result = PollResult(
            scanned=0,
            inserted=0,
            deleted=0,
            paused=True,
            message="Monitoring is paused. Resume before polling.",
        )
        store.record_run(found=0, message=result.message)
        return result

    scanned = 0
    inserted = 0
    try:
        for subreddit in settings.subreddits:
            posts = provider.list_new_posts(subreddit, limit=settings.poll_limit)
            for post in posts:
                scanned += 1
                if post.removed:
                    continue
                verdict = evaluate_post(post, settings.keywords, settings.exclude_terms)
                if not verdict.matched:
                    continue
                if store.upsert_match(
                    reddit_fullname=post.fullname,
                    subreddit=post.subreddit or subreddit,
                    title=post.title,
                    url=post.url,
                    author=post.author,
                    created_utc=post.created_utc,
                    matched_keywords=list(verdict.keywords),
                    community_note=settings.note_for(post.subreddit or subreddit),
                ):
                    inserted += 1
        deleted = reconcile_deletions(provider, store)
        message = (
            f"Polled {len(settings.subreddits)} subreddit(s); "
            f"scanned {scanned}; new matches {inserted}; marked deleted {deleted}."
        )
        store.record_run(found=inserted, message=message)
        return PollResult(
            scanned=scanned,
            inserted=inserted,
            deleted=deleted,
            paused=False,
            message=message,
        )
    except RedditError as exc:
        message = f"Poll failed: {exc}"
        store.record_run(found=0, message=message, error=str(exc))
        return PollResult(
            scanned=scanned,
            inserted=inserted,
            deleted=0,
            paused=False,
            message=message,
            error=str(exc),
        )


def reconcile_deletions(provider: RedditProvider, store: Store, batch_size: int = 50) -> int:
    """Mark stored posts deleted when Reddit no longer returns them or flags removal."""
    fullnames = store.known_fullnames()
    deleted = 0
    for i in range(0, len(fullnames), batch_size):
        batch = fullnames[i : i + batch_size]
        for post in provider.fetch_posts_by_fullname(batch):
            if post.removed and store.mark_fullname_deleted(post.fullname):
                deleted += 1
    return deleted
