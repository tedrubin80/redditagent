"""Web dashboard for read-only Reddit match review.

Optional HTTP basic auth via DASHBOARD_USER / DASHBOARD_PASSWORD when exposing
beyond localhost. No remote auth by default — set credentials before binding
publicly.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import secrets
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .config import AppPaths
from .monitor import poll_once
from . import secrets as _secrets
from .settings import MonitorSettings
from .store import Store
from .treg_reddit import TregError, TregRedditProvider

PHASE = "phase4-treg"
STATIC_DIR = Path(__file__).resolve().parent / "static"


def _paths() -> AppPaths:
    return AppPaths.from_env()


def _store() -> Store:
    return Store(_paths().db_path)


def _load_settings() -> MonitorSettings:
    return MonitorSettings.load(_paths().settings_path)


def _make_provider() -> TregRedditProvider:
    """Return the treg.to Reddit provider. Raises if TREG_TOKEN is not configured."""
    token = _secrets.get_treg_token(_paths().data_dir)
    if not token:
        raise ValueError(
            "TREG_TOKEN is not configured. Open the dashboard and use the Setup tab to enter your token — get one at https://treg.to"
        )
    return TregRedditProvider(token)


def _is_configured() -> bool:
    """True when a treg token is available (env or secrets file)."""
    return bool(_secrets.get_treg_token(_paths().data_dir))


def _provider_name() -> str:
    return "treg"


def _auth_configured() -> tuple[str, str] | None:
    return _secrets.get_dashboard_creds(_paths().data_dir)


def _settings_payload(settings: MonitorSettings | None = None, error: str | None = None) -> dict:
    if error:
        return {"ok": False, "error": error, "settings": None}
    assert settings is not None
    return {
        "ok": True,
        "error": None,
        "settings": {
            "project_name": settings.project_name,
            "subreddits": list(settings.subreddits),
            "keywords": list(settings.keywords),
            "exclude_terms": list(settings.exclude_terms),
            "poll_limit": settings.poll_limit,
            "community_notes": dict(settings.community_notes),
        },
    }


def _status_payload() -> dict:
    store = _store()
    status = store.status()
    try:
        settings_block = _settings_payload(_load_settings())
    except ValueError as exc:
        settings_block = _settings_payload(error=str(exc))
    creds = _auth_configured()
    return {
        "phase": PHASE,
        "provider": _provider_name(),
        "configured": _is_configured(),
        "paused": status.paused,
        "last_run_at": status.last_run_at,
        "last_error": status.last_error,
        "last_found": status.last_found,
        "last_message": status.last_message,
        "counts": store.counts(),
        "auth_required": creds is not None,
        "dashboard_user_set": creds is not None,
        **settings_block,
    }


def _post_to_dict(post) -> dict:
    return {
        "fullname": post.fullname,
        "subreddit": post.subreddit,
        "title": post.title,
        "url": post.url,
        "author": post.author,
        "created_utc": post.created_utc,
        "selftext": post.selftext,
    }


def _match_dict(match) -> dict:
    return {
        "id": match.id,
        "reddit_fullname": match.reddit_fullname,
        "subreddit": match.subreddit,
        "title": match.title,
        "url": match.url,
        "author": match.author,
        "created_utc": match.created_utc,
        "matched_keywords": list(match.matched_keywords),
        "community_note": match.community_note,
        "status": match.status,
        "created_at": match.created_at,
        "updated_at": match.updated_at,
    }


def _save_settings(raw: dict) -> MonitorSettings:
    settings = MonitorSettings.from_dict(raw)
    path = _paths().settings_path
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "project_name": settings.project_name,
        "subreddits": list(settings.subreddits),
        "keywords": list(settings.keywords),
        "exclude_terms": list(settings.exclude_terms),
        "poll_limit": settings.poll_limit,
        "community_notes": dict(settings.community_notes),
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    return settings


class Handler(BaseHTTPRequestHandler):
    server_version = "RedditAgent/0.3"

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        # Health stays unauthenticated for container probes.
        if path == "/health":
            return self._json(200, {"status": "ok", "phase": PHASE, "paused": _store().get_paused(), "configured": _is_configured()})
        # /api/setup is open (no auth gate) so the dashboard can bootstrap.
        if path == "/api/setup":
            creds = _auth_configured()
            return self._json(200, {
                "configured": _is_configured(),
                "dashboard_user_set": creds is not None,
                "dashboard_user": creds[0] if creds else "",
            })
        if not self._authorized():
            return self._unauthorized()
        if path in ("/", "/index.html"):
            return self._send_static("index.html")
        if path.startswith("/static/"):
            return self._send_static(path[len("/static/") :])
        if path == "/api/status":
            return self._json(200, _status_payload())
        if path == "/api/matches":
            qs = parse_qs(parsed.query)
            include_ignored = qs.get("include_ignored", ["0"])[0] == "1"
            status_filter = (qs.get("status", [""])[0] or "").strip().lower()
            try:
                limit = min(500, max(1, int(qs.get("limit", ["100"])[0])))
            except ValueError:
                limit = 100
            matches = _store().list_matches(include_ignored=include_ignored or bool(status_filter), limit=limit)
            if status_filter:
                matches = [m for m in matches if m.status == status_filter]
            return self._json(200, {"matches": [_match_dict(m) for m in matches]})
        if path == "/api/settings":
            try:
                return self._json(200, _settings_payload(_load_settings()))
            except ValueError as exc:
                return self._json(404, _settings_payload(error=str(exc)))

        if path == "/api/search":
            qs = parse_qs(parsed.query)
            query = (qs.get("q", [""])[0] or "").strip()
            subreddit = (qs.get("subreddit", [""])[0] or "").strip().lstrip("r/") or None
            try:
                limit = min(50, max(1, int(qs.get("limit", ["25"])[0])))
            except ValueError:
                limit = 25
            sort = (qs.get("sort", ["relevance"])[0] or "relevance").strip()
            timeframe = (qs.get("t", ["all"])[0] or "all").strip()
            if not query:
                return self._json(400, {"ok": False, "error": "q (search query) is required"})
            try:
                posts = _make_provider().search_posts(
                    query, subreddit=subreddit, limit=limit, sort=sort, timeframe=timeframe
                )
                return self._json(200, {
                    "ok": True,
                    "query": query,
                    "subreddit": subreddit,
                    "results": [_post_to_dict(p) for p in posts],
                })
            except (ValueError, TregError) as exc:
                return self._json(502, {"ok": False, "error": str(exc)})

        if path.startswith("/api/matches/") and path.endswith("/comments"):
            parts = path.split("/")
            # /api/matches/<id>/comments → parts = ['', 'api', 'matches', '<id>', 'comments']
            try:
                match_id = int(parts[3])
            except (IndexError, ValueError):
                return self._json(400, {"ok": False, "error": "Invalid match id"})
            match = _store().get_match(match_id)
            if match is None:
                return self._json(404, {"ok": False, "error": "Match not found"})
            qs = parse_qs(parsed.query)
            try:
                limit = min(200, max(1, int(qs.get("limit", ["100"])[0])))
            except ValueError:
                limit = 100
            try:
                comments = _make_provider().fetch_comments(match.url, limit=limit)
                return self._json(200, {"ok": True, "match_id": match_id, "comments": comments})
            except (ValueError, TregError) as exc:
                return self._json(502, {"ok": False, "error": str(exc)})

        self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        raw = self._read_body()
        content_type = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()

        # /api/setup is open when nothing is configured yet (bootstrap);
        # once a token is saved it requires dashboard auth.
        if path == "/api/setup":
            already_configured = _is_configured()
            if already_configured and not self._authorized():
                return self._unauthorized()
            data = self._parse_body(raw, content_type)
            token = str(data.get("treg_token") or "").strip()
            dash_user = str(data.get("dashboard_user") or "").strip()
            dash_pass = str(data.get("dashboard_password") or "").strip()
            if not token and not already_configured:
                return self._json(400, {"ok": False, "error": "treg_token is required"})
            updates: dict = {}
            if token:
                updates["treg_token"] = token
            if dash_user:
                updates["dashboard_user"] = dash_user
            if dash_pass:
                updates["dashboard_password"] = dash_pass
            # Clearing dashboard creds explicitly
            if data.get("clear_dashboard_auth"):
                updates["dashboard_user"] = ""
                updates["dashboard_password"] = ""
            if updates:
                _secrets.save(_paths().data_dir, updates)
            return self._json(200, {
                "ok": True,
                "configured": _is_configured(),
                "dashboard_user_set": _auth_configured() is not None,
            })

        if not self._authorized():
            return self._unauthorized()

        if path == "/api/poll" or path == "/poll":
            store = _store()
            try:
                settings = _load_settings()
                provider = _make_provider()
                result = poll_once(provider, settings, store)
                payload = {
                    "ok": True,
                    "found": result.inserted,
                    "scanned": result.scanned,
                    "deleted": result.deleted,
                    "paused": result.paused,
                    "message": result.message,
                    "status": _status_payload(),
                }
                if path == "/poll":
                    return self._redirect("/")
                return self._json(200, payload)
            except (ValueError, TregError) as exc:
                store.record_run(found=0, message=f"Poll failed: {exc}", error=str(exc))
                if path == "/poll":
                    return self._redirect("/")
                return self._json(400, {"ok": False, "error": str(exc), "status": _status_payload()})

        if path == "/api/pause" or path == "/pause":
            data = self._parse_body(raw, content_type)
            paused_raw = data.get("paused", True)
            if isinstance(paused_raw, list):
                paused = paused_raw[0] in ("1", "true", "True", True)
            elif isinstance(paused_raw, str):
                paused = paused_raw in ("1", "true", "True")
            else:
                paused = bool(paused_raw)
            _store().set_paused(paused)
            if path == "/pause":
                return self._redirect("/")
            return self._json(200, {"ok": True, "paused": paused, "status": _status_payload()})

        if path == "/api/check":
            try:
                provider = _make_provider()
                provider.check_connection()
                return self._json(200, {"ok": True, "message": "treg.to connection succeeded.", "provider": "treg"})
            except (ValueError, TregError) as exc:
                return self._json(400, {"ok": False, "error": str(exc)})

        if path == "/ignore":
            form = parse_qs(raw.decode("utf-8", errors="replace"))
            try:
                match_id = int(form.get("id", [""])[0])
            except (TypeError, ValueError):
                return self.send_error(400, "Missing match id")
            _store().set_status(match_id, "ignored")
            return self._redirect("/")

        if path.startswith("/api/matches/") and path.endswith("/status"):
            try:
                match_id = int(path.split("/")[3])
            except (IndexError, ValueError):
                return self._json(400, {"ok": False, "error": "Invalid match id"})
            data = self._parse_body(raw, content_type)
            status = data.get("status")
            if isinstance(status, list):
                status = status[0] if status else None
            if not isinstance(status, str):
                return self._json(400, {"ok": False, "error": "status is required"})
            try:
                updated = _store().set_status(match_id, status)
            except ValueError as exc:
                return self._json(400, {"ok": False, "error": str(exc)})
            if not updated:
                return self._json(404, {"ok": False, "error": "Match not found"})
            return self._json(200, {"ok": True, "id": match_id, "status": status})

        self.send_error(404)

    def do_PUT(self):
        if not self._authorized():
            return self._unauthorized()
        parsed = urlparse(self.path)
        if parsed.path != "/api/settings":
            return self.send_error(404)
        raw = self._read_body()
        content_type = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        data = self._parse_body(raw, content_type)
        if not isinstance(data, dict) or "project_name" not in data:
            # Accept either the settings object directly or wrapped.
            if isinstance(data, dict) and isinstance(data.get("settings"), dict):
                data = data["settings"]
            else:
                return self._json(400, {"ok": False, "error": "JSON settings object required"})
        try:
            settings = _save_settings(data)
        except ValueError as exc:
            return self._json(400, {"ok": False, "error": str(exc)})
        return self._json(200, _settings_payload(settings))

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args), file=sys.stderr)

    def _authorized(self) -> bool:
        creds = _auth_configured()
        if creds is None:
            return True
        header = self.headers.get("Authorization", "")
        if not header.startswith("Basic "):
            return False
        try:
            decoded = base64.b64decode(header[6:].strip()).decode("utf-8")
            user, _, password = decoded.partition(":")
        except Exception:
            return False
        expected_user, expected_password = creds
        return secrets.compare_digest(user, expected_user) and secrets.compare_digest(
            password, expected_password
        )

    def _unauthorized(self) -> None:
        body = b'{"ok":false,"error":"Unauthorized"}'
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Reddit Agent"')
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0") or 0)
        return self.rfile.read(length) if length else b""

    def _parse_body(self, raw: bytes, content_type: str):
        if not raw:
            return {}
        if content_type == "application/json":
            try:
                return json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                return {}
        form = parse_qs(raw.decode("utf-8", errors="replace"))
        return {k: v[0] if len(v) == 1 else v for k, v in form.items()}

    def _send_static(self, relative: str) -> None:
        # Explicit allowlist — do not serve arbitrary paths.
        allowed = {"index.html", "app.css", "app.js"}
        name = Path(relative).name
        if name not in allowed:
            return self.send_error(404)
        file_path = STATIC_DIR / name
        if not file_path.is_file():
            return self.send_error(404)
        data = file_path.read_bytes()
        if name.endswith(".js"):
            ctype = "application/javascript; charset=utf-8"
        elif name.endswith(".css"):
            ctype = "text/css; charset=utf-8"
        elif name.endswith(".html"):
            ctype = "text/html; charset=utf-8"
        else:
            ctype = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
        self._send(200, data, ctype)

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self._send(code, body, "application/json")

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, location: str) -> None:
        body = (
            "<!doctype html><title>Redirecting</title>"
            f'<a href="{location}">Continue</a>'
            f"<script>location.replace({location!r});</script>"
        ).encode()
        self.send_response(303)
        self.send_header("Location", location)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    host = os.environ.get("BIND_HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8080"))
    if host in ("0.0.0.0", "::") and _auth_configured() is None:
        print(
            "WARNING: Binding on all interfaces without DASHBOARD_USER/DASHBOARD_PASSWORD.",
            file=sys.stderr,
        )
    print(f"Reddit Agent dashboard on http://{host}:{port}", file=sys.stderr)
    ThreadingHTTPServer((host, port), Handler).serve_forever()
