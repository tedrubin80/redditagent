# Reddit Agent

A self-hosted, human-led Reddit research assistant inspired by the [LURK approach](https://metaflow.life/blog/how-to-build-reddit-ai-agent) (Listen → Understand → Reply → Keep). This repo implements **foundation + read-only listening** with a browser dashboard: app-only OAuth, keyword matching against allowlisted subreddits, SQLite match storage, pause/ignore/review controls, settings editor, and light deletion reconciliation.

It does **not** generate AI replies or post on Reddit.

## Quick start with Docker

1. Copy `.env.example` to `.env` and edit the values locally. Use an existing, approved Reddit **confidential** app's client ID and secret. Set `DASHBOARD_USER` / `DASHBOARD_PASSWORD` before exposing the port beyond a trusted network. Do not commit or share `.env`.
2. Copy `config/settings.example.json` to `data/settings.json` and edit project, subreddits, keywords, and community notes.
3. Complete the [Phase 1 checklist](docs/PHASE1_CHECKLIST.md) before treating live matches as authorized for your use case.
4. Run `docker compose up --build -d` (or `./scripts/start.sh`).
5. Open the dashboard:
   - Local: http://127.0.0.1:8080
   - Network / VPS URL: `http://<server-ip>:8080` (browser will prompt for dashboard login if credentials are set)
6. Connection check: use **Check Reddit** in the UI, or `docker compose run --rm app python -m agent.check_reddit`
7. One-shot poll: **Run poll** in the UI, or `docker compose run --rm app python -m agent.run_monitor`

The Reddit helpers make network requests only when you invoke the connection check or a poll. They verify technical access, not authorization for a particular business use. Never put credentials in a GitHub issue or repository.

### Compose tips

```bash
# Custom host port
HOST_PORT=8080 docker compose up --build -d

# Follow logs
docker compose logs -f app
```

## Without Docker

Requires Python 3.11 or newer, no external packages. Export the variables shown in `.env.example` in your shell; `.env` is loaded by Compose, not Python automatically.

```bash
mkdir -p data
cp config/settings.example.json data/settings.json
export DATA_DIR="$PWD/data"
export SETTINGS_PATH="$PWD/data/settings.json"
export DB_PATH="$PWD/data/agent.db"
# also export REDDIT_* (and optional DASHBOARD_*) from .env.example

python3 -m agent.server
python3 -m agent.check_reddit
python3 -m agent.run_monitor
python3 -m unittest discover -s tests -v
```

## Dashboard

The web UI (served from the same Docker container) lets you:

- See live status, last poll message, and match counts
- Run a poll, pause/resume monitoring, and verify Reddit credentials
- Filter the match queue and mark items reviewing / done / ignored
- Edit allowlisted subreddits, keywords, excludes, and community notes

JSON APIs: `/api/status`, `/api/matches`, `/api/settings`, `/api/poll`, `/api/pause`, `/api/check`, `/api/matches/<id>/status`. `/health` stays open for container probes.

## What works now

| Capability | Status |
|---|---|
| Browser dashboard (Docker URL) | Yes |
| Optional HTTP basic auth | Yes |
| App-only OAuth connectivity check | Yes |
| Allowlisted subreddit + keyword poll | Yes |
| Exclude terms, dedupe, ignore, pause, review states | Yes |
| In-browser settings editor | Yes |
| Deletion reconciliation via `/api/info` | Yes (best-effort) |
| AI draft replies | Not yet (Phase 4) |
| Posting to Reddit | Not yet / optional gated (Phase 5) |

See [the phased project plan](docs/PROJECT_PLAN.md) for architecture, milestones, policy gates, and acceptance criteria.
