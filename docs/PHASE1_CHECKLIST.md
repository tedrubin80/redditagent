# Phase 1 — Access and requirements checklist

Complete these decisions before relying on read-only monitoring against live Reddit data. Technical auth alone is not permission.

## Access and policy

- [ ] Confirm the Reddit app type (confidential / other) and that client-credentials (app-only) OAuth is allowed for the intended reads.
- [ ] Confirm the original approval purpose covers the intended business or project use; stop or revise scope if it does not.
- [ ] Record approved scopes, rate limits, and any commercial or data-processing terms.
- [ ] Confirm whether Reddit content may be sent to any LLM provider later (Phase 4). Default: do not send until approved.
- [ ] Note Reddit’s announced public API transition (target March 2027) and whether Devvit or another path is required later.

## MVP scope

- [ ] Choose the first project name (for example LegitFests or YarnCompass).
- [ ] Choose a small allowlist of subreddits (prefer clear rules and active moderation).
- [ ] Define include keywords and exclude terms (avoid promo/spam bait).
- [ ] Document each community’s rules, flair rules, and promo stance in `community_notes`.
- [ ] Confirm the human-review workflow: matches appear in the local dashboard; humans decide; no auto-posting.

## Local setup

- [ ] Copy `.env.example` → `.env` and set real credentials locally (never commit).
- [ ] Copy `config/settings.example.json` → `data/settings.json` (or set `SETTINGS_PATH`) and edit the allowlist.
- [ ] Run `python3 -m agent.check_reddit` successfully against the real confidential app.
- [ ] Keep the dashboard bound to localhost until Phase 3 authentication exists.

## Exit

Phase 1 is done when the boxes above are decided in writing, the credential check succeeds on Ted’s machine, and MVP scope is reflected in `settings.json`. If permissions do not support the use, do not scrape or bypass controls—revise scope instead.
