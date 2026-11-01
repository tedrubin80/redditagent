# Reddit Agent

A self-hosted, human-led Reddit research assistant inspired by the [LURK approach](https://metaflow.life/blog/how-to-build-reddit-ai-agent) (Listen → Understand → Reply → Keep). This repo currently implements **foundation + read-only listening**: a local dashboard, app-only OAuth, keyword matching against an allowlisted set of subreddits, SQLite match storage, pause/ignore controls, and light deletion reconciliation.

It does **not** generate AI replies or post on Reddit.

## Quick start with Docker

1. Copy `.env.example` to `.env` and edit the values locally. Use an existing, approved Reddit **confidential** app's client ID and secret. Do not commit or share `.env`.
2. Copy `config/settings.example.json` to `data/settings.json` and edit project, subreddits, keywords, and community notes.
3. Complete the [Phase 1 checklist](docs/PHASE1_CHECKLIST.md) before treating live matches as authorized for your use case.
4. Run `docker compose up --build`.
5. Open http://127.0.0.1:8080. The server binds to localhost by default and has no login; do not expose it publicly.
6. Connection check: `docker compose run --rm app python -m agent.check_reddit`
7. One-shot poll: `docker compose run --rm app python -m agent.run_monitor` (or use **Run poll** on the dashboard)

The Reddit helpers make network requests only when you invoke the connection check or a poll. They verify technical access, not authorization for a particular business use. Never put credentials in a GitHub issue or repository.

## Without Docker

Requires Python 3.11 or newer, no external packages. Export the variables shown in `.env.example` in your shell; `.env` is loaded by Compose, not Python automatically.

```bash
mkdir -p data
cp config/settings.example.json data/settings.json
export DATA_DIR="$PWD/data"
export SETTINGS_PATH="$PWD/data/settings.json"
export DB_PATH="$PWD/data/agent.db"
# also export REDDIT_* from .env.example

python3 -m agent.server
python3 -m agent.check_reddit
python3 -m agent.run_monitor
python3 -m unittest discover -s tests -v
```

## What works now

| Capability | Status |
|---|---|
| Local status / match dashboard | Yes |
| App-only OAuth connectivity check | Yes |
| Allowlisted subreddit + keyword poll | Yes |
| Exclude terms, dedupe, ignore, pause | Yes |
| Deletion reconciliation via `/api/info` | Yes (best-effort) |
| AI draft replies | Not yet (Phase 4) |
| Posting to Reddit | Not yet / optional gated (Phase 5) |

See [the phased project plan](docs/PROJECT_PLAN.md) for architecture, milestones, policy gates, and acceptance criteria.
