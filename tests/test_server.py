import base64
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
        # Ensure auth off unless a test sets it.
        os.environ.pop("DASHBOARD_USER", None)
        os.environ.pop("DASHBOARD_PASSWORD", None)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self._patcher.stop()
        self.tmp.cleanup()

    def _request(self, method: str, path: str, body: str | None = None, headers: dict | None = None):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=5)
        hdrs = dict(headers or {})
        payload = None
        if body is not None:
            payload = body.encode()
            hdrs.setdefault("Content-Type", "application/json")
            hdrs["Content-Length"] = str(len(payload))
        conn.request(method, path, body=payload, headers=hdrs)
        resp = conn.getresponse()
        raw = resp.read()
        location = resp.getheader("Location")
        status = resp.status
        conn.close()
        return status, location, raw

    def _get(self, path: str, headers: dict | None = None):
        status, _, body = self._request("GET", path, headers=headers)
        return status, body

    def _post(self, path: str, body: str, content_type="application/x-www-form-urlencoded"):
        status, location, raw = self._request(
            "POST",
            path,
            body=body,
            headers={"Content-Type": content_type},
        )
        return status, location, raw

    def test_health_phase(self):
        status, body = self._get("/health")
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertIn("phase", payload)

    def test_dashboard_serves_spa(self):
        status, body = self._get("/")
        self.assertEqual(status, 200)
        text = body.decode()
        self.assertIn("Reddit Agent", text)
        self.assertIn("/static/app.js", text)

    def test_static_assets(self):
        status, body = self._get("/static/app.js")
        self.assertEqual(status, 200)
        self.assertIn(b"/api/poll", body)

    def test_api_matches(self):
        status, body = self._get("/api/matches")
        self.assertEqual(status, 200)
        matches = json.loads(body)["matches"]
        self.assertEqual(matches[0]["title"], "Archive question")

    def test_ignore_match_form(self):
        status, location, body = self._post("/ignore", "id=1")
        self.assertEqual(status, 303)
        self.assertEqual(location, "/")
        self.assertIn(b"location.replace", body)
        _, matches_body = self._get("/api/matches")
        self.assertEqual(json.loads(matches_body)["matches"], [])

    def test_status_api_json(self):
        status, _, body = self._request(
            "POST",
            "/api/matches/1/status",
            body=json.dumps({"status": "reviewing"}),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["ok"])
        _, matches_body = self._get("/api/matches")
        self.assertEqual(json.loads(matches_body)["matches"][0]["status"], "reviewing")

    def test_pause(self):
        status, _, body = self._post("/pause", "paused=1")
        self.assertEqual(status, 303)
        self.assertIn(b"location.replace", body)
        _, payload = self._get("/api/status")
        self.assertTrue(json.loads(payload)["paused"])

    def test_save_settings(self):
        payload = {
            "project_name": "demo-2",
            "subreddits": ["genealogy"],
            "keywords": ["census"],
            "exclude_terms": [],
            "poll_limit": 10,
            "community_notes": {"genealogy": "Be careful with living people"},
        }
        status, _, body = self._request(
            "PUT",
            "/api/settings",
            body=json.dumps(payload),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 200)
        saved = json.loads(body)["settings"]
        self.assertEqual(saved["project_name"], "demo-2")
        self.assertEqual(saved["subreddits"], ["genealogy"])

    def test_basic_auth_required(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        with patch.dict(
            os.environ,
            {**self.env, "DASHBOARD_USER": "ted", "DASHBOARD_PASSWORD": "secret"},
            clear=False,
        ):
            self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            self.port = self.httpd.server_address[1]
            self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
            self.thread.start()
            status, body = self._get("/")
            self.assertEqual(status, 401)
            token = base64.b64encode(b"ted:secret").decode()
            status, body = self._get("/", headers={"Authorization": f"Basic {token}"})
            self.assertEqual(status, 200)
            # Health remains open for probes.
            status, _ = self._get("/health")
            self.assertEqual(status, 200)


if __name__ == "__main__":
    unittest.main()
