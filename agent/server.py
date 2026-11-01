"""Local-only dashboard for read-only match review. No remote auth yet — bind to localhost."""
from __future__ import annotations

import html
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

from .config import AppPaths, RedditConfig
from .monitor import poll_once
from .reddit import OAuthRedditProvider, RedditError
from .settings import MonitorSettings
from .store import Store

PHASE = "phase2-monitoring"


def _paths() -> AppPaths:
    return AppPaths.from_env()


def _store() -> Store:
    return Store(_paths().db_path)


def _load_settings():
    return MonitorSettings.load(_paths().settings_path)


def _page() -> bytes:
    store = _store()
    status = store.status()
    counts = store.counts()
    matches = store.list_matches(limit=50)
    settings_error = ""
    project = "(settings not loaded)"
    subs = []
    try:
        settings = _load_settings()
        project = settings.project_name
        subs = list(settings.subreddits)
    except ValueError as exc:
        settings_error = str(exc)

    rows = []
    for match in matches:
        keywords = ", ".join(match.matched_keywords)
        note = match.community_note or "—"
        rows.append(
            "<tr>"
            f"<td><a href=\"{html.escape(match.url)}\" rel=\"noopener noreferrer\" target=\"_blank\">"
            f"{html.escape(match.title)}</a><br><small>r/{html.escape(match.subreddit)} · "
            f"u/{html.escape(match.author)}</small></td>"
            f"<td>{html.escape(keywords)}</td>"
            f"<td>{html.escape(note)}</td>"
            f"<td>{html.escape(match.status)}</td>"
            "<td>"
            f"<form method=\"post\" action=\"/ignore\" style=\"display:inline\">"
            f"<input type=\"hidden\" name=\"id\" value=\"{match.id}\">"
            "<button type=\"submit\">Ignore</button></form>"
            "</td>"
            "</tr>"
        )
    table = (
        "<table><thead><tr><th>Thread</th><th>Matched</th><th>Community note</th>"
        "<th>Status</th><th></th></tr></thead><tbody>"
        + ("".join(rows) if rows else "<tr><td colspan=\"5\">No open matches yet. Run a poll.</td></tr>")
        + "</tbody></table>"
    )
    paused_label = "paused" if status.paused else "active"
    error_block = (
        f"<p class=\"warn\">Last error: {html.escape(status.last_error)}</p>"
        if status.last_error
        else ""
    )
    settings_block = (
        f"<p class=\"warn\">Settings: {html.escape(settings_error)}</p>"
        if settings_error
        else f"<p>Project <strong>{html.escape(project)}</strong> · watching "
        f"{html.escape(', '.join('r/' + s for s in subs) or '(none)')}</p>"
    )
    body = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Reddit Agent</title>
<style>
body{{font:16px/1.55 system-ui,sans-serif;background:#111827;color:#e5e7eb;max-width:960px;margin:4vh auto;padding:24px}}
section{{background:#1f2937;border-radius:12px;padding:20px 24px;margin:16px 0}}
h1{{margin:0 0 4px}} .muted{{color:#9ca3af}} strong{{color:#fdba74}}
code,small{{color:#a7f3d0}} .warn{{color:#fca5a5}}
table{{width:100%;border-collapse:collapse;font-size:15px}}
th,td{{text-align:left;padding:10px 8px;border-bottom:1px solid #374151;vertical-align:top}}
th{{color:#9ca3af;font-weight:600}}
a{{color:#93c5fd}} button,.btn{{background:#374151;color:#e5e7eb;border:0;border-radius:8px;padding:8px 12px;cursor:pointer}}
form.inline{{display:inline-block;margin-right:8px}}
.actions{{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}}
</style>
</head>
<body>
<h1>Reddit Agent</h1>
<p class="muted">Human-led research · LURK Listen stage · no posting</p>
<section>
<strong>Status: {paused_label}</strong>
{settings_block}
<p>Last run: <code>{html.escape(status.last_run_at or 'never')}</code>
· new last poll: <code>{status.last_found}</code>
· open: <code>{counts.get('new', 0)}</code>
· ignored: <code>{counts.get('ignored', 0)}</code>
· deleted: <code>{counts.get('deleted', 0)}</code></p>
<p>{html.escape(status.last_message or 'No poll yet. Use Run poll or python -m agent.run_monitor.')}</p>
{error_block}
<div class="actions">
<form class="inline" method="post" action="/poll"><button type="submit">Run poll</button></form>
<form class="inline" method="post" action="/pause"><input type="hidden" name="paused" value="{0 if status.paused else 1}">
<button type="submit">{'Resume' if status.paused else 'Pause'}</button></form>
</div>
</section>
<section>
<strong>Match queue</strong>
<p class="muted">Matches are advisory. Review community rules before engaging. AI drafts and posting are not implemented.</p>
{table}
</section>
</body>
</html>"""
    return body.encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "RedditAgent/0.2"

    def do_GET(self):
        if self.path == "/":
            return self._send(200, _page(), "text/html; charset=utf-8")
        if self.path == "/health":
            payload = {"status": "ok", "phase": PHASE, "paused": _store().get_paused()}
            return self._send(200, json.dumps(payload).encode(), "application/json")
        if self.path == "/api/status":
            store = _store()
            status = store.status()
            payload = {
                "phase": PHASE,
                "paused": status.paused,
                "last_run_at": status.last_run_at,
                "last_error": status.last_error,
                "last_found": status.last_found,
                "last_message": status.last_message,
                "counts": store.counts(),
            }
            return self._send(200, json.dumps(payload).encode(), "application/json")
        if self.path == "/api/matches":
            matches = [
                {
                    "id": m.id,
                    "reddit_fullname": m.reddit_fullname,
                    "subreddit": m.subreddit,
                    "title": m.title,
                    "url": m.url,
                    "author": m.author,
                    "matched_keywords": list(m.matched_keywords),
                    "community_note": m.community_note,
                    "status": m.status,
                }
                for m in _store().list_matches(limit=100)
            ]
            return self._send(200, json.dumps({"matches": matches}).encode(), "application/json")
        self.send_error(404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length) if length else b""
        form = parse_qs(raw.decode("utf-8", errors="replace"))
        if self.path == "/pause":
            paused = (form.get("paused", ["1"])[0] == "1")
            _store().set_paused(paused)
            return self._redirect("/")
        if self.path == "/ignore":
            try:
                match_id = int(form.get("id", [""])[0])
            except (TypeError, ValueError):
                return self.send_error(400, "Missing match id")
            _store().set_status(match_id, "ignored")
            return self._redirect("/")
        if self.path == "/poll":
            store = _store()
            try:
                settings = _load_settings()
                provider = OAuthRedditProvider(RedditConfig.from_env())
                poll_once(provider, settings, store)
            except (ValueError, RedditError) as exc:
                store.record_run(found=0, message=f"Poll failed: {exc}", error=str(exc))
            return self._redirect("/")
        self.send_error(404)

    def log_message(self, fmt, *args):
        # Keep stdout clean; avoid logging query strings that might include secrets later.
        sys_stderr = __import__("sys").stderr
        print("%s - %s" % (self.address_string(), fmt % args), file=sys_stderr)

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, location: str) -> None:
        # 303 is correct after POST; also emit a tiny HTML fallback for clients
        # that do not auto-follow the redirect.
        body = (
            "<!doctype html><title>Redirecting</title>"
            f"<a href=\"{location}\">Continue</a>"
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
    ThreadingHTTPServer((host, port), Handler).serve_forever()
