import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from agent.matching import evaluate_post
from agent.monitor import poll_once, reconcile_deletions
from agent.reddit import RedditPost
from agent.settings import MonitorSettings
from agent.store import Store


def _post(**overrides):
    base = dict(
        fullname="t3_abc",
        subreddit="askhistorians",
        title="Looking for a primary source archive",
        selftext="Any tips?",
        url="https://www.reddit.com/r/askhistorians/comments/abc/x/",
        permalink="/r/askhistorians/comments/abc/x/",
        author="alice",
        created_utc=1_700_000_000.0,
        removed=False,
    )
    base.update(overrides)
    return RedditPost(**base)


class MatchingTests(unittest.TestCase):
    def test_keyword_hit(self):
        result = evaluate_post(_post(), ("archive",), ("buy now",))
        self.assertTrue(result.matched)
        self.assertEqual(result.keywords, ("archive",))

    def test_exclude_wins(self):
        result = evaluate_post(
            _post(title="Best archive buy now"),
            ("archive",),
            ("buy now",),
        )
        self.assertFalse(result.matched)
        self.assertEqual(result.excluded_by, "buy now")


class SettingsTests(unittest.TestCase):
    def test_load_settings(self):
        raw = {
            "project_name": "demo",
            "subreddits": ["AskHistorians", "r/testing"],
            "keywords": ["archive"],
            "exclude_terms": ["buy now"],
            "poll_limit": 10,
            "community_notes": {"askhistorians": "Sources required"},
        }
        settings = MonitorSettings.from_dict(raw)
        self.assertEqual(settings.subreddits, ("askhistorians", "testing"))
        self.assertEqual(settings.note_for("AskHistorians"), "Sources required")

    def test_rejects_empty_keywords(self):
        with self.assertRaisesRegex(ValueError, "keywords"):
            MonitorSettings.from_dict(
                {"project_name": "x", "subreddits": ["a"], "keywords": []}
            )


class StoreAndPollTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "agent.db"
        self.store = Store(self.db)
        self.settings = MonitorSettings.from_dict(
            {
                "project_name": "demo",
                "subreddits": ["askhistorians"],
                "keywords": ["archive"],
                "exclude_terms": ["promo code"],
                "poll_limit": 25,
                "community_notes": {"askhistorians": "Sources required"},
            }
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_dedup_and_ignore(self):
        post = _post()
        self.assertTrue(
            self.store.upsert_match(
                reddit_fullname=post.fullname,
                subreddit=post.subreddit,
                title=post.title,
                url=post.url,
                author=post.author,
                created_utc=post.created_utc,
                matched_keywords=["archive"],
                community_note="Sources required",
            )
        )
        self.assertFalse(
            self.store.upsert_match(
                reddit_fullname=post.fullname,
                subreddit=post.subreddit,
                title=post.title,
                url=post.url,
                author=post.author,
                created_utc=post.created_utc,
                matched_keywords=["archive"],
                community_note="Sources required",
            )
        )
        match = self.store.list_matches()[0]
        self.assertTrue(self.store.set_status(match.id, "ignored"))
        self.assertEqual(self.store.list_matches(), [])

    def test_poll_inserts_matches(self):
        provider = MagicMock()
        provider.list_new_posts.return_value = [
            _post(),
            _post(fullname="t3_skip", title="Unrelated question", selftext="hello"),
            _post(fullname="t3_promo", title="Archive promo code deal", selftext=""),
        ]
        provider.fetch_posts_by_fullname.return_value = []
        result = poll_once(provider, self.settings, self.store)
        self.assertIsNone(result.error)
        self.assertEqual(result.inserted, 1)
        self.assertEqual(len(self.store.list_matches()), 1)
        self.assertEqual(self.store.list_matches()[0].matched_keywords, ("archive",))

    def test_pause_blocks_poll(self):
        self.store.set_paused(True)
        provider = MagicMock()
        result = poll_once(provider, self.settings, self.store)
        self.assertTrue(result.paused)
        provider.list_new_posts.assert_not_called()

    def test_reconcile_marks_deleted(self):
        self.store.upsert_match(
            reddit_fullname="t3_gone",
            subreddit="askhistorians",
            title="Gone",
            url="https://www.reddit.com/r/askhistorians/comments/gone/x/",
            author="bob",
            created_utc=1.0,
            matched_keywords=["archive"],
            community_note="",
        )
        provider = MagicMock()
        provider.fetch_posts_by_fullname.return_value = [
            _post(fullname="t3_gone", removed=True, author="[deleted]", selftext="[removed]")
        ]
        deleted = reconcile_deletions(provider, self.store)
        self.assertEqual(deleted, 1)
        self.assertEqual(self.store.counts().get("deleted"), 1)

    def test_settings_file_roundtrip(self):
        path = Path(self.tmp.name) / "settings.json"
        path.write_text(
            json.dumps(
                {
                    "project_name": "demo",
                    "subreddits": ["askhistorians"],
                    "keywords": ["archive"],
                }
            ),
            encoding="utf-8",
        )
        loaded = MonitorSettings.load(path)
        self.assertEqual(loaded.project_name, "demo")


if __name__ == "__main__":
    unittest.main()
