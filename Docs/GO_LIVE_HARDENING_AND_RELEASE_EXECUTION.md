# GO_LIVE_HARDENING_AND_RELEASE_EXECUTION.md

## 1) Current Status (as of February 17, 2026)

- Backend test suite passes: `17/17`.
- Frontend production build passes.
- Core API modules for Sprints 1-9 are present.
- CI now enforces:
  - backend tests
  - backend dependency vulnerability scan (`pip-audit`)
  - frontend lint
  - frontend build
  - frontend dependency vulnerability scan (`npm audit --audit-level=high`)

## 2) What Is Still Missing Before Production

### A) Missing real provider integrations (current logic is synthetic/demo in multiple modules)

You still need live data providers for:

- Rank collection provider + proxy network.
- Local reviews/profile provider (Google Business Profile data source).
- Backlink and citation provider(s).
- Email delivery provider for report sending.
- Object storage for report artifacts (instead of local filesystem paths).

### B) Missing production platform components

- Docker Desktop (or another container runtime) on your machine for local full-stack parity.
- A production host/platform (AWS/GCP/Azure/Render/Fly/etc.).
- Managed PostgreSQL.
- Managed Redis.
- HTTPS/TLS and domain routing (reverse proxy / load balancer).
- Monitoring/alerting stack (logs, metrics, uptime alerts, error tracking).
- Secrets manager for credentials and keys.

### C) Security/config gaps to close

- Production JWT key management (rotate off local/dev secret patterns).
- Production environment variables from `Docs/ENVIRONMENT_AND_CONFIG_SPEC.md` must be populated.
- Security scan needs to run cleanly in CI and before release approval.

## 3) APIs: Missing vs Present

- Missing LSOS product API endpoints from the sprint roadmap: **none identified**.
- Missing capability is mostly **integration depth**, not route count:
  - Existing endpoints return/generated synthetic values in several services until provider APIs are wired.

## 4) Exact Step-by-Step Actions (Non-Technical Operator Version)

Follow these in order. Do not skip.

1. Install Docker Desktop
- Download and install Docker Desktop for Windows.
- Reboot if installer requests it.
- Open Docker Desktop once and wait for engine status to show as running.

2. Verify full local stack runs
- Open terminal in project root.
- Run: `docker compose up --build`
- Wait until services show healthy startup logs.
- Keep this terminal open.

3. Verify backend and frontend from browser
- Open `http://localhost:3000` (frontend).
- Open `http://localhost:8000/api/v1/health` (API health).
- Confirm health response contains `"status": "ok"`.

4. Verify CI pipeline is green
- Push current branch to GitHub.
- Open GitHub Actions.
- Confirm every job is green:
  - backend test
  - backend `pip-audit`
  - frontend lint
  - frontend build
  - frontend `npm audit`

5. Set up production services (managed, not local)
- Create a managed PostgreSQL database.
- Create a managed Redis instance.
- Create object storage bucket for reports.
- Create transactional email account/provider.
- Create monitoring account (error tracking + uptime + logs).

6. Fill production secrets/config
- In your deployment platform, define all required production environment variables from:
  - `Docs/ENVIRONMENT_AND_CONFIG_SPEC.md`
- Use strong real secrets, not sample/local values.
- Keep all secrets in platform secret manager, not in code files.

7. Wire live provider integrations (engineering task)
- Connect real SERP/rank provider and proxy provider.
- Connect local profile/reviews provider.
- Connect backlink/citation provider sources.
- Connect real report email sending provider.
- Connect object storage upload for report artifacts.

8. Run staging validation (must pass before production)
- Deploy to staging environment.
- Run full smoke flow:
  - login
  - create campaign
  - crawl
  - rank
  - competitors
  - content
  - local/reviews
  - authority/citations
  - intelligence score/recommendations
  - report generate + deliver
- Confirm no cross-tenant data leakage.

9. Run release checklist and sign-off
- Use:
  - `Docs/OPERATIONS_RUNBOOK.md`
  - `Docs/SRE_SLOS_AND_ALERTING.md`
  - `Docs/RELEASE_AND_CHANGE_MANAGEMENT.md`
  - `Docs/MIGRATION_AND_DATA_GOVERNANCE.md`
- Confirm rollback procedure is tested and documented.
- Confirm on-call ownership and alert routes are assigned.

10. Production go-live execution
- Schedule a release window.
- Deploy backend + worker + scheduler + frontend.
- Run post-deploy smoke test immediately.
- Watch logs/metrics for 60 minutes.
- If critical errors appear: execute rollback policy in `Docs/RELEASE_AND_CHANGE_MANAGEMENT.md`.

## 5) Simple Decision Rule

Do **not** launch to production until:

- All CI jobs are green.
- Staging smoke flow is fully green.
- Real provider integrations are connected.
- Monitoring and rollback are proven.
