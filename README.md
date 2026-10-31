# Reddit Agent

A self-hosted, human-led Reddit research assistant. This initial scaffold provides a local status page, a read-only Reddit OAuth connection check, Docker packaging, and a phased project plan. It does **not** monitor subreddits, generate AI responses, or post on Reddit yet.

## Quick start with Docker

1. Copy `.env.example` to `.env` and edit the values locally. Use an existing, approved Reddit **confidential** app's client ID and secret. Do not commit or share `.env`.
2. Run `docker compose up --build`.
3. Open http://127.0.0.1:8080. The server binds to localhost by default and has no login; do not expose it publicly.
4. To test Reddit credentials, run `docker compose run --rm app python -m agent.check_reddit`. The check requests an app-only token and reads Reddit's scopes endpoint. It does not post or access a user account. This grant requires a confidential app with a secret; other app types require a different OAuth flow.

The check makes real network requests only when invoked. It verifies technical access, not authorization for a particular use. Your existing access may be subject to its approved purpose and Reddit's current policies. Never put credentials in a GitHub issue or repository.

## Without Docker

Requires Python 3.11 or newer, no external packages. Export the variables shown in `.env.example` in your shell; `.env` is loaded by Compose, not Python automatically.

```bash
python -m agent.server
python -m agent.check_reddit
python -m unittest discover -s tests -v
```

See [the phased project plan](docs/PROJECT_PLAN.md) for architecture, milestones, policy gates, and acceptance criteria.
