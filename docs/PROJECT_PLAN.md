# Reddit Agent: project plan

**Status:** Phase 2 read-only monitoring in progress (Phase 0 foundation shipped). Phase 1 access decisions remain a human checklist. This document is a proposed roadmap, not a claim that later AI/posting features exist. Last reviewed October 31, 2026.

## Goal

Give Ted a self-hosted workspace to find relevant Reddit discussions, assess community rules, and prepare useful, candid responses for human review. The system should support different projects (for example LegitFests or YarnCompass) without presenting promotion as independent advice. Decisions on target communities and projects remain open.

## Ground rules and dependencies

- Existing Reddit credentials are valuable, but verify the scope of the original approval and whether the intended business use is authorized. Technical authentication alone does not establish permission. Confirm permitted use, data retention, approved AI processing, and any commercial agreement with Reddit before implementing dependent features.
- Respect Reddit and subreddit rules; disclose affiliation where relevant. Obtain moderator permission where required. Never impersonate a human-operated account with an automated agent, use unsolicited automated DMs, evade limits, or automate account creation. Human review does not itself grant API or content-use permission.
- Do not train or fine-tune models on Reddit content without the necessary rights and express authorization. Verify provider data handling before sending content to any AI service.
- Reddit has announced plans to end remaining public API access in March 2027. Verify current transition guidance, any account-specific exceptions, and whether Devvit supports the actual use case before committing to an implementation. Devvit is not a guaranteed replacement for a cross-subreddit marketing agent. Build to a provider interface so the external API can be replaced without rewriting the entire app.
- Remove deleted Reddit content and author data in accordance with current terms; build deletion reconciliation before persistent ingestion. Use minimum retention and avoid copies in logs or third-party analytics.
- Policy references (check again before release): [Data API](https://support.reddithelp.com/hc/en-us/articles/16160319875092-Reddit-Data-API-Wiki), [Developer access](https://support.reddithelp.com/hc/en-us/articles/14945211791892-Developer-Platform-Accessing-Reddit-Data), [platform rules](https://support.reddithelp.com/hc/en-us/articles/360043512931-Don-t-break-the-site), [API transition](https://developers.reddit.com/app-registration), [Devvit rules](https://developers.reddit.com/docs/devvit_rules).

## Architecture target

`Reddit adapter → ingestion and filtering → review queue → optional AI draft → human decision`

Aligned with Metaflow’s LURK framing: **Listen** (allowlisted monitoring), **Understand** (community notes / rules context), **Reply** (human-approved helpful drafts later), **Keep** (logs, pause, deletion reconciliation).

A local web dashboard controls project settings and displays only authorized data. Polling is explicit (CLI or dashboard button) in Phase 2; a scheduled worker can come later. Client-side pacing (~60 req/min) plus 429 backoff is included. SQLite is the initial store. AI is optional and lives behind a provider interface later. API credentials remain in environment variables, never in Git or browser code. Posting is a separate gated phase, not part of the MVP.

## Mapping to the Metaflow guide

| LURK step | This repo |
|---|---|
| Listen | Phase 2: `agent.monitor` + allowlisted settings |
| Understand | Phase 1/2: `community_notes` + human review of rules |
| Reply | Phase 4 drafts; Phase 5 optional posting (gated) |
| Keep | Phase 2+: SQLite match history, pause switch, deletion marks, status API |

## Phase 0 — Foundation (shipped)

**Deliverables:** Python standard-library service and status page; configuration template; explicitly invoked app-only OAuth check; Docker/Compose; basic tests; this plan. No background activity, Reddit data collection, AI calls or posting.

**Done when:** service starts locally, health endpoint responds, tests pass, credentials are excluded from Git, and the connection check reports clear errors without exposing credentials. A real credential test is still needed on Ted's machine. The check requires a confidential app supporting client-credentials OAuth; other credential types need a separate flow.

## Phase 1 — Access and requirements

- Confirm approved app type, API scopes, original authorization, intended commercial use and rate limits with Reddit as needed. Verify what will remain available after the announced transition.
- Select first project, purpose, communities, keywords, excluded terms and human-review workflow. Document each community's rules and approval requirements.
- Decide whether Reddit content may be sent to the chosen LLM provider under current terms, and whether an integration must run on Devvit.

**Working docs:** [PHASE1_CHECKLIST.md](PHASE1_CHECKLIST.md) and `config/settings.example.json`.

**Exit:** documented approval/permission decisions, selected MVP scope and a credential check against the real app. If permissions do not support the proposed use, stop that integration and revise scope; do not scrape or bypass access controls.

## Phase 2 — Read-only monitoring (current build)

- Add a Reddit provider interface and authorized implementation; support OAuth as appropriate for approved credentials. Consume documented limits and respond to 429s with backoff; no limit bypass.
- Configure a small allowlist of subreddits, keywords, polling frequency, deduplication and exclusion rules. Provide a pause switch and explicit last-run/error status.
- Reconcile deleted content and accounts, implement retention and minimal audit logs, and verify behavior against Reddit's current deletion requirements before persisting data.
- Display matched threads with links, rule context, reasons for a match and an ignore action.

**Implemented in-repo:** `OAuthRedditProvider`, JSON settings allowlist, SQLite store, `run_monitor` / dashboard poll, pause + ignore, keyword/exclude matching, `/api/info` deletion reconciliation, mocked unit tests. Still open: Ted’s live credential pilot, retention policy validation, and scheduled (non-manual) polling if desired.

**Exit:** tests with mocked API responses, rate limits, deletions and failures; approved real-world read-only pilot produces relevant matches without posting. Exact retention needs policy validation.

## Phase 3 — Review dashboard and security

- Implement queue states: new, reviewing, dismissed and completed; project filters and searchable settings. Display source links and allow correcting rules manually.
- Add real authentication with hashed passwords, sessions, CSRF protection, secure cookies, appropriate authorization and rate limiting before any remote exposure. Localhost-only remains the default until then.
- Add data export/deletion, safe backups, structured logs that exclude secrets and unnecessary Reddit content, health checks and basic deployment documentation.

**Exit:** a user can log in securely, review and dismiss items, recover from restart and delete stored data. Test authorization and session behavior; review deployment security.

## Phase 4 — AI-assisted drafts

- Add optional provider interfaces (e.g., OpenRouter or another approved provider), model selection, key management, explicit cost limits and request timeouts. Confirm provider-specific data and policy terms first; no provider is presumed approved for every integration.
- Generate a draft using relevant thread context and project facts; clearly show source and affiliation. Display uncertainty and let Ted edit, regenerate, discard or copy.
- Drafting is advisory. Do not invent facts, auto-insert promotional links, store model training data, or send content to unapproved providers.

**Exit:** mock-provider and end-to-end tests, explicit user-triggered draft generation, readable cost/error handling and no publication. Verify results manually for accuracy and subreddit fit.

## Phase 5 — Optional posting integration

- Reassess Reddit permissions and subreddit rules; determine if this phase is permitted and wanted. It may be unavailable under future platform restrictions.
- If authorized, implement user-delegated OAuth, least-privilege scopes, an explicit confirmation for each post, preview, disclosure, retries designed to prevent duplicate submissions, audit metadata and a global stop control. Never automate unsolicited outreach.
- Alternatively, keep a copy-and-open workflow where Ted manually posts.

**Exit:** demonstrate no post occurs without specific user confirmation; test revoked tokens, failures, duplicate prevention and pause control. No automatic replies by default.

## Phase 6 — Operations and evolution

- Deployment and recovery: Docker Compose upgrades, encrypted backups, monitoring, data deletion reconciliation, credential rotation, versioned migrations and incident handling.
- Track useful measures: relevant matches, manual approvals, dismissals, errors and removals—not just engagement or link clicks. Review community feedback and stop where unwelcome.
- Revisit Reddit access and Devvit feasibility ahead of the 2027 transition. Migrate only if the required use case and policy terms are supported.

**Exit:** a documented operating routine, tested restore, verified deletion processing, and a decision on continuing, migrating or retiring the integration.

## Open decisions

1. Which project and communities first? 2. Is existing Reddit approval commercial, personal, or use-specific? 3. Where will it run? 4. Which AI provider, if permitted? 5. Is manual copy/paste sufficient or is eventual approved posting desired?
