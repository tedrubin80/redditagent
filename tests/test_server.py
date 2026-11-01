import json
import os
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch

from http.server import ThreadingHTTPServer

from agent.server import Handler
from agent.store import Store


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        self.db = self.data / "agent.db"
        self.settings = self.data / "settings.json"
        self.settings.write_text(
            json.dumps(
                {
                    "project_name": "demo",
                    "subreddits": ["askhistorians"],
                    "keywords": ["archive"],
                }
            ),
            encoding="utf-8",
        )
        self.env = {
            "DATA_DIR": str(self.data),
            "SETTINGS_PATH": str(self.settings),
            "DB_PATH": str(self.db),
        }
        store = Store(self.db)
        store.upsert_match(
            reddit_fullname="t3_1",
            subreddit="askhistorians",
            title="Archive question",
            url="https://www.reddit.com/r/askhistorians/comments/1/x/",
            author="alice",
            created_utc=1.0,
            matched_keywords=["archive"],
            community_note="Sources required",
        )
        self._patcher = patch.dict(os.environ, self.env, clear=False)
        self._patcher.start()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self._patcher.stop()
        self.tmp.cleanup()

    def _get(self, path: str):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", path)
        resp = conn.getresponse()
        body = resp.read()
        conn.close()
        return resp.status, body

    def _post(self, path: str, body: str):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request(
            "POST",
            path,
            body=body.encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp = conn.getresponse()
        raw = resp.read()
        conn.close()
        return resp.status, resp.getheader("Location"), raw

    def test_health_phase(self):
        status, body = self._get("/health")
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertEqual(payload["phase"], "phase2-monitoring")

    def test_dashboard_lists_match(self):
        status, body = self._get("/")
        self.assertEqual(status, 200)
        text = body.decode()
        self.assertIn("Archive question", text)
        self.assertIn("Sources required", text)

    def test_ignore_match(self):
        status, location, body = self._post("/ignore", "id=1")
        self.assertEqual(status, 303)
        self.assertEqual(location, "/")
        self.assertIn(b"location.replace", body)
        _, matches_body = self._get("/api/matches")
        self.assertEqual(json.loads(matches_body)["matches"], [])

    def test_pause(self):
        status, _, body = self._post("/pause", "paused=1")
        self.assertEqual(status, 303)
        self.assertIn(b"location.replace", body)
        _, payload = self._get("/api/status")
        self.assertTrue(json.loads(payload)["paused"])


if __name__ == "__main__":
    unittest.main()
