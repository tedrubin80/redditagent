"""Local-only foundation status page. No secrets, writes, or remote calls."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os

HTML = b'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Reddit Agent</title><style>body{font:16px system-ui;background:#111827;color:#e5e7eb;max-width:760px;margin:8vh auto;padding:24px;line-height:1.6}section{background:#1f2937;border-radius:12px;padding:24px}h1{margin-bottom:0}strong{color:#fdba74}code{color:#a7f3d0}</style></head><body><h1>Reddit Agent</h1><p>Human-led community research</p><section><strong>Foundation running</strong><p>This is the starting point for your dashboard. Monitoring, AI drafts and posting are not implemented yet.</p><p>Run the connection check from your terminal when you are ready. See the project plan for the next phases.</p></section></body></html>'''

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            body, content_type = HTML, "text/html; charset=utf-8"
        elif self.path == "/health":
            body, content_type = json.dumps({"status": "ok", "phase": "foundation"}).encode(), "application/json"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

if __name__ == "__main__":
    ThreadingHTTPServer((os.environ.get("BIND_HOST", "127.0.0.1"), 8080), Handler).serve_forever()
