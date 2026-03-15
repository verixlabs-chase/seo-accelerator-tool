# Master System Audit

## 1. Executive Summary

This repo is a backend-heavy local SEO operations platform with a usable but narrow tenant UI, a thin platform admin UI, a very large amount of architectural ambition, and a major truth gap between "system breadth in code" and "sellable product breadth in UX."

What is real:
- A FastAPI backend with a broad route surface and a large SQLAlchemy model set.
- A Next.js frontend that meaningfully ships six tenant product pages plus a basic platform control surface.
- Auth, campaign creation, crawl scheduling, rank scheduling, report generation, execution governance, and platform control all exist in code.
- CI exists and frontend lint/build passed locally.
- The backend has a large automated test suite by file count.

What is not yet real enough:
- A coherent, trustworthy non-technical-user product.
- Honest completion across local SEO, authority, competitor, reporting, and automation surfaces.
- Production-grade observability, external integration depth, and operator-safe execution at scale.
- A launch-ready commercial platform for agencies or mainstream SMB operators.

Bottom line: this is not a fake repo, but it is also not a launch-ready product. It is a substantial engineering foundation carrying a lot of speculative system mass and too much "enterprise architecture" relative to the product experience actually shipped.

## 2. Overall Project Verdict

Overall verdict: **usable foundation, not launch-ready**.

Classification:
- `product`: incomplete, misleading
- `frontend`: usable, underbuilt
- `backend`: usable, overbuilt
- `architecture`: overbuilt, fragile
- `automation`: ambitious, unsafe-to-overtrust
- `launch`: not launch-ready

The repo can support internal demos, continued build-out, and targeted operator-led workflows. It should not be represented as a mature autonomous SEO platform, an agency-ready white-label platform, or a non-technical SMB-ready product.

## 3. What This Product Really Is Today

Today this product is:
- A local-search operations workbench with campaign setup, scan/rank/report loops, some platform control tooling, and a governed execution concept.
- A mostly operator-led system where the dashboard still exposes manual forms for campaign creation, crawl triggering, rank checks, and report sending in `frontend/app/(product)/dashboard/page.tsx`.
- A product where many "advanced" capabilities exist as backend modules, schemas, tests, and docs, but are not turned into complete user workflows.
- A system still dependent on synthetic, fixture, or thin-provider behavior in multiple areas, explicitly acknowledged in `docs/enterprise_architecture/go_live_hardening_and_release_execution.md`.

## 4. What It Pretends To Be But Is Not Yet

It currently presents itself, by naming and surface area, as if it is:
- A full-spectrum local SEO intelligence platform.
- A robust automated execution engine.
- A broad agency portfolio platform.
- A deeply operationalized enterprise system with hardened observability and governance.
- A product understandable by non-technical business owners.

It is not yet those things in a commercially honest sense because:
- Major user-facing surfaces are missing entirely: no shipped competitor page, content page, authority page, citations page, settings page, or locations page in the frontend route tree.
- Hidden nav items exist for routes that do not exist: `/settings`, `/locations`, `/competitors` in `frontend/app/(product)/nav.config.ts`.
- The platform UI is plain HTML-table admin tooling, not a serious operator console.
- Reporting is functionally present but artifact quality is primitive; HTML is inline and PDF generation is a hand-built text PDF in `backend/app/services/reporting_service.py`.
- Provider-backed features are thin or synthetic; several defaults rely on synthetic backends while docs themselves admit missing real integrations.

## 5. System Strengths

- The backend is not toy-sized. It has real breadth, consistent routing, models, migrations, task infrastructure, and governance concepts.
- The repo has unusually high test breadth by file count for a project at this maturity level.
- Execution workflows are at least attempting idempotency, approvals, rollback, and mutation audit persistence.
- The platform has a meaningful org/tenant/role model instead of a purely fake single-tenant shortcut.
- There is evidence of disciplined thinking around replay, governance, eventing, and failure modes.
- Frontend build health is decent: `npm run lint` and `npm run build` passed locally.
- Local full-stack startup is possible with Docker plus a separate frontend dev server.

## 6. System Weaknesses

- Product truthfulness is weak. The codebase looks broader and more mature than the user experience actually is.
- UX closure is weak. The dashboard remains a mixed marketing panel plus operator control panel plus onboarding shell.
- The codebase is documentation-heavy and audit-heavy to a degree that signals repeated self-analysis without enough simplification.
- Architecture has outpaced productization.
- Observability is partly real and partly memory-local/in-process, which is not credible for scaled production claims.
- Local and authority providers default to `synthetic`, but synthetic providers are blocked outside `APP_ENV=test`, creating configuration contradictions.
- Security posture is not strong enough for launch: tokens in `localStorage`, dev secrets in examples, rate limiting disabled by default, and permissive local assumptions.
- The frontend has no test suite.

## 7. Product / UX Audit

Classification: `usable`, `underbuilt`, `not launch-ready`

Findings:
- The root page and login are clean enough visually, but they overpromise simplicity relative to the system’s real complexity.
- The dashboard is the main product surface, but it still contains raw manual operator forms under "Advanced controls" for campaign creation, scans, rank checks, and reports. That is not a finished end-user product shape.
- The dashboard tries to soften this by demoting the controls, but they still drive core workflow completion.
- Onboarding exists through `OnboardingWizard.tsx`, but the product still depends heavily on dashboard-side manual actions, so onboarding and operations are not cleanly separated.
- Reports, rankings, local visibility, opportunities, and site health each have productized shells, but much of the experience is "query API, display summary cards, offer manual actions." This is usable, but thin.
- The platform admin area (`frontend/app/platform/*`) is functionally crude. It is serviceable internal tooling, not polished operator software.
- Empty states are better than average in the tenant product pages, but workflow closure is still weak because many suggested next actions route back to dashboard manual tools.
- Non-technical clarity is not strong enough. The UI uses plain-English labels in many places, but the product logic still assumes operator understanding of scans, position checks, schedules, campaigns, approvals, and execution status.
- Mobile readiness is likely acceptable for layout, but there is no evidence of mobile-specific QA or interaction testing.

Truth assessment:
- The tenant UX is better than the backend breadth would suggest.
- The tenant UX is still not credible as a finished SMB product.

## 8. Frontend Engineering Audit

Classification: `usable`, `underbuilt`, `maintainable`, `not launch-ready`

Evidence:
- Actual route tree is small: root, login, dashboard, rankings, reports, opportunities, local-visibility, site-health, and platform pages.
- No frontend tests were found.
- `next.config.mjs` disables lint during build with `eslint: { ignoreDuringBuilds: true }`.
- Next warns about ambiguous workspace root because the repo has multiple lockfiles.

Findings:
- The route structure is understandable, but the shipped UI surface is far narrower than the product narrative.
- State management is entirely local component state plus direct fetch wrappers; this is fine at current size but will become brittle as workflows grow.
- API integration patterns are simple and repeated; there is no typed client layer, caching layer, or normalized data model.
- Auth stores access and refresh tokens in `localStorage` in `frontend/app/login/page.jsx` and `frontend/app/platform/api.js`. That is a weak browser-security posture.
- The product shell components are reasonably cohesive.
- The platform admin pages use bare inline styles and tables, completely separate from the tenant design language, which makes the system feel split-brain.
- There are hidden nav entries for unshipped routes. Even hidden, this indicates route/feature drift.
- Frontend build health is okay today, but confidence is lower than it looks because there is no frontend test coverage.

## 9. Backend Engineering Audit

Classification: `usable`, `overbuilt`, `fragile`, `not launch-ready`

Strengths:
- Route organization is disciplined in `backend/app/api/v1/router.py`.
- Auth, campaigns, reports, executions, platform control, and provider credentials are all implemented in a coherent enough way.
- The model and migration surface is very broad and suggests sustained engineering effort.
- Execution paths attempt approval, retry, rollback, idempotency, and mutation audit persistence.

Weaknesses:
- The backend is much broader than the product can honestly surface.
- Many domains are still thin implementations with simple formulas or placeholder-like logic behind serious names.
- `reporting_service.py` generates simplistic KPI summaries and a barebones PDF artifact. This is functional, not product-grade reporting.
- `intelligence_service.py` computes composite scores and recommendations with simplistic heuristics, while route naming and docs imply something much more sophisticated.
- `dashboard_service.py` derives "platform state" from lightweight in-process observability snapshots. That is not a real platform health plane.
- `automation.py` exposes timeline/export endpoints directly over raw event rows; there is no deeper operator workflow there.
- A lot of code looks built to satisfy architecture shape before proving product value.

Key truth gap:
- The backend has the shape of a larger platform than the business product can currently justify.

## 10. Testing / CI / Reliability Audit

Classification: `usable`, `strong in breadth`, `fragile in confidence`

Evidence:
- Backend tests are extensive by file count.
- Frontend lint and build passed locally.
- CI workflows exist for backend, frontend, replay gate, and preflight.
- The backend test harness in `backend/tests/conftest.py` is sophisticated and includes migration parity checks and database setup logic.

Findings:
- Test breadth is high, but breadth is not the same as confidence.
- Many tests appear to validate schemas, transitions, or internal contracts, not necessarily realistic end-user truth.
- Some tests explicitly tolerate synthetic/provider-thin paths.
- Load tests exist, but repo evidence suggests many performance scenarios are synthetic or monkeypatched rather than production-like.
- There is no frontend test suite, which is a major blind spot for the actual shipped user experience.
- The backend suite was still running during audit sampling, so I do not have a final full local pass/fail result from `pytest -q`.
- CI is duplicated and uneven: `ci.yml` and `backend-ci.yml` overlap; `backend-ci.yml` relies heavily on Docker Compose and references a specific `test_performance_envelope.py` path, while `ci.yml` also runs backend tests directly.
- `next lint` is already deprecated, so the frontend lint path is on borrowed time.

Reliability judgment:
- Better than average engineering discipline.
- Still too easy to develop false confidence from test count and workflow count.

## 11. Local Dev / DX Audit

Classification: `usable`, `fragile`

Evidence:
- README provides startup instructions.
- Docker Compose works for core infra and API.
- Frontend and backend are started separately.
- Preflight script exists in `infra/go-live-preflight.ps1`.

Findings:
- Local startup works, but it is not smooth.
- The backend docs imply `backend/.env`, but the active local behavior also depends on repo-root `.env`, which is easy to confuse.
- Docker Compose emits warnings for unset Google OAuth variables by default.
- Frontend startup warns about ambiguous workspace root because of multiple lockfiles.
- Frontend is not part of Compose despite README wording that can imply a fuller stack.
- There are many local virtualenv remnants and caches in the repo, which is a signal of uneven environment hygiene.
- Preflight is PowerShell-first, which is fine for cross-platform ambition but clumsy for a WSL/Linux-centered local workflow.

DX truth:
- A determined engineer can run this repo.
- A normal operator or non-technical owner cannot.

## 12. Architecture / Scalability Audit

Classification: `overbuilt`, `fragile`, `not yet scalable in a trustable way`

Strengths:
- The system thinks about queues, worker profiles, governance, replay, eventing, and background orchestration.
- There is explicit separation between tenant APIs and control-plane APIs.
- The project is at least trying to model org, sub-account, location, business location, portfolio, and provider policy concepts.

Weaknesses:
- Significant parts of the observability model are in-process memory (`backend/app/services/observability_service.py`), which collapses under multi-process or multi-instance deployment.
- Many background tasks still directly call service code in ways that are fine for today but not evidence of robust distributed execution.
- The architecture includes many high-order systems before the core user workflows are fully productized.
- The database model count and migration volume are high relative to the amount of proven user-facing value.
- Complexity is growing faster than product leverage.

Scalability judgment:
- Architecturally ambitious.
- Operationally unproven.

## 13. Security / Safety / Governance Audit

Classification: `fragile`, `unsafe to overstate`, `not launch-ready`

Strengths:
- There is real role-aware auth and organization membership enforcement.
- Execution approval, rejection, rollback, and audit logging are present.
- Provider credentials are encrypted-at-rest via the credential service.
- Production config validation exists.

Weaknesses:
- Browser auth tokens live in `localStorage`, which is a poor default for a system with privileged execution workflows.
- `.env.example` includes weak local secrets; understandable for dev, but the repo is not clearly hardened against operator misuse.
- Rate limiting is disabled by default.
- Metrics auth is optional and disabled by default.
- Some admin and execution safety is implemented, but product messaging can still make the system look safer than it is.
- Safety claims exceed runtime maturity because provider integrations, observability, and rollback paths are not deeply proven in production-like conditions.

Governance judgment:
- Better than typical early-stage projects conceptually.
- Not yet strong enough to justify strong automation-trust claims.

## 14. Automation / Execution Audit

Classification: `usable in controlled conditions`, `fragile`, `unsafe for aggressive trust`

What is real:
- Recommendation executions exist with schedule, run, retry, cancel, approve, reject, and rollback endpoints.
- Mutation persistence exists.
- A WordPress execution plugin and transport path exist.

What is fragile:
- Recommendation quality is still thin.
- Execution types are narrow and mapped from recommendation categories through a small registry.
- Governance depends partly on local or simplistic policy logic.
- Automation/export endpoints are mostly history exposure, not a rich operations loop.
- The WordPress path is promising, but this is still an integration that needs hardening, version control discipline, site-specific safety validation, and production telemetry.

Critical truth:
- This is an automation foundation, not a trustable autonomous execution product.

## 15. Reporting / Summaries Audit

Classification: `usable`, `underbuilt`

Evidence:
- Report generation, schedule, retrieval, and delivery endpoints exist.
- Tenant reports page is shipped.
- Report status is surfaced in the dashboard.

Weaknesses:
- Report content is simplistic KPI packaging, not differentiated client-grade reporting.
- HTML artifact handling is effectively inline.
- PDF generation is text-based and minimal.
- Storage is local filesystem by default via `generated_reports`.
- Email delivery provider depth is still not what a white-label or agency product would require.

Judgment:
- Reporting is implemented.
- Reporting is not yet impressive, premium, or white-label strong.

## 16. Agency / White-Label / Portfolio Audit

Classification: `incomplete`, `misleading if overstated`

Evidence:
- Organizations, sub-accounts, provider policies, platform admin roles, and portfolio-related models exist.
- Platform org and provider-health pages exist.

Weaknesses:
- The frontend agency/operator experience is far too thin.
- No white-label polish is present in shipped reports or tenant-branding workflows.
- Platform admin pages are internal CRUD/control surfaces, not mature agency operations tools.
- There is not enough operator-grade billing, support, portfolio rollup UX, or client-facing artifact quality to call this agency-ready.

## 17. Competitive Readiness Audit

Classification: `not ready`

Findings:
- The repo has real leverage in execution governance concepts and technical breadth.
- The shipped product experience does not yet compete well with mature SEO tools on trust, clarity, or workflow completion.
- The product currently risks competing on architectural ambition rather than operator value.
- For SMBs, it is too complex.
- For agencies, it is too unfinished.
- For enterprises, the runtime proof and operational evidence are too weak.

## 18. Feature Completeness Audit

Classification: `misleading`, `incomplete`

Completed enough to count:
- Auth
- Campaign creation/listing
- Crawl scheduling and issue viewing
- Rank keyword add/schedule/trend view
- Basic reports workflow
- Basic platform org control
- Execution governance primitives

Not completed enough to count as finished product features:
- Competitors as a user-facing workflow
- Content/authority/citations as a usable product
- White-label reporting
- Agency portfolio control
- Non-technical onboarding
- Real provider-backed local SEO operations
- Trustworthy autonomous recommendations

## 19. Workflow Closure Audit

Classification: `fragile`

Core workflow closure today:
- Login -> dashboard -> create campaign -> run crawl -> run rank -> generate report

This closes technically, but weakly:
- It relies on manual operator steps.
- It does not feel like a finished journey.
- It does not close the loop into confident, repeatable business outcomes.

The biggest closure problem:
- The repo has many side systems, but the primary user loop still depends on operator initiative rather than cleanly guided outcomes.

## 20. Top Technical Risks

1. Architectural sprawl outruns maintainability and product value.
2. Observability is overstated relative to real multi-instance readiness.
3. Browser token storage is weak for privileged workflows.
4. Provider-backed features are thin and sometimes configuration-contradictory.
5. Reporting artifacts are too primitive for premium/client-facing use.
6. Frontend has no automated tests.
7. Execution automation is safer than a naive system, but not safe enough to oversell.
8. The codebase has high migration/model complexity relative to the shipped product surface.

## 21. Top Product Risks

1. Users will assume more capability than the product can honestly deliver.
2. Non-technical users will not understand what to do next without assistance.
3. Agency users will see backend promise but insufficient operator tooling.
4. Report quality will undersell the platform.
5. Hidden or absent surfaces create feature expectation drift.

## 22. Top GTM / Readiness Risks

1. Sales story will outrun product truth.
2. Demoability is stronger than repeatable customer value.
3. White-label and agency narratives are ahead of product delivery.
4. Missing provider depth makes many "real-world" claims fragile.
5. Launching too early will create credibility damage, not just bugs.

## 23. What Is Overbuilt

- The architecture and model surface.
- Replay/governance/eventing complexity relative to current product adoption proof.
- The amount of documentation and audit material.
- The number of backend domains not yet turned into credible workflows.
- The test corpus relative to the maturity of the frontend and product journey.

## 24. What Is Underbuilt

- Frontend test coverage.
- End-user workflow closure.
- Platform/operator UX.
- Report quality and artifact delivery.
- Non-technical onboarding clarity.
- Real provider-backed data collection.
- White-label readiness.
- Production observability and hardened runtime operations.

## 25. What Should Be Simplified

- The dashboard’s role as both product shell and raw operator console.
- The narrative around "intelligence" until recommendation quality justifies it.
- The architecture/documentation surface that currently exceeds product leverage.
- Duplicated CI concepts.
- The distinction between internal admin tooling and productized operator tooling.

## 26. What Should Be Productized Next

- A single coherent tenant journey from onboarding to first useful report.
- Rankings and site health as the first two truly excellent product modules.
- Report review/delivery with client-grade artifact quality.
- Honest opportunities/executions UI with clear approval and risk language.
- A real platform operator console only after tenant workflows are trustworthy.

## 27. What Should Not Be Touched Yet

- The basic auth/org/role model.
- Execution audit persistence and rollback concepts.
- Provider credential encryption patterns.
- The core route modularization.
- The existing design direction of the tenant shell, which is decent enough to refine rather than replace.

## 28. Scorecard

| Area | Score (1-10) | Classification | Why |
|---|---:|---|---|
| Product clarity | 4 | misleading | Product story is broader than actual shipped experience. |
| UX quality | 5 | usable | Tenant pages are cleaner than expected, but workflow closure is weak. |
| Frontend quality | 6 | usable | Shipped pages are coherent and build cleanly, but no frontend tests and weak auth storage. |
| Backend quality | 7 | usable | Serious breadth and structure, but too much thin logic under ambitious naming. |
| Architecture quality | 5 | overbuilt | Strong concepts, but too much system mass before proving product value. |
| Test quality | 6 | usable | Strong breadth, but likely some false-confidence risk and no frontend coverage. |
| CI reliability | 6 | usable | CI exists and is meaningful, but duplicated and partly aging. |
| Local dev reliability | 5 | fragile | Runnable, but messy, warning-heavy, and not streamlined. |
| Execution safety | 5 | fragile | Better than average guardrails, still not safe enough to oversell automation. |
| Reporting quality | 4 | underbuilt | Functional reports, weak premium/client-grade output. |
| Automation maturity | 5 | usable | Real mechanisms exist, but recommendation quality and runtime proof are not mature. |
| Agency readiness | 3 | incomplete | Internal control-plane foundations exist; agency product does not. |
| Competitive readiness | 3 | not launch-ready | Too unfinished versus real category expectations. |
| Scalability readiness | 4 | fragile | Architectural intent is there; operational proof is not. |
| Security / governance readiness | 5 | fragile | Some solid controls, but important launch-grade gaps remain. |
| Maintainability | 5 | fragile | Good modularity, but excessive breadth and system sprawl are mounting costs. |
| Launch readiness | 3 | not launch-ready | Not honest or safe enough for a broad launch. |
| Non-technical-user readiness | 3 | incomplete | Too operator-shaped and concept-heavy. |
| Operator readiness | 5 | usable | Internal operators can work with it, but tooling is still thin and uneven. |
| Overall system maturity | 5 | usable | Real system, real leverage, not a mature product. |

## 29. Final Priority Stack

1. Product truthfulness
2. Workflow closure
3. Report quality
4. Provider-backed reality
5. Frontend hardening
6. Operator console quality
7. Observability hardening
8. Architecture simplification
9. Agency packaging
10. Scale tuning

## 30. Final Recommendation

Do not expand breadth further until the existing tenant product is made honest, coherent, and trustworthy.

The right move is not "build more systems." The right move is:
- simplify the product story,
- harden the core user loop,
- improve report quality,
- make provider-backed modules honest,
- and only then decide which advanced systems deserve continued investment.

This repo has real leverage. It also has a serious risk of disappearing into architecture theater if it keeps adding surface area faster than it converts capability into reliable product value.

## Top 25 actions in priority order

| # | Action | Why it matters | Area | Severity | Effort | Recommended sequence |
|---|---|---|---|---|---|---|
| 1 | Remove or demote every product claim that exceeds shipped UX reality | Prevents trust damage and aligns roadmap with truth | Product | Critical | Low | First |
| 2 | Redesign the dashboard around one primary operator journey instead of mixed panels plus raw tools | Current dashboard is structurally honest but product-confused | Product | Critical | Medium | First |
| 3 | Decide the first truly productized wedge: rankings + site health + reports, or local visibility + reports | The repo is too broad; it needs a narrow commercial core | Product | Critical | Medium | First |
| 4 | Upgrade report artifacts from text-grade output to polished client-grade summaries | Reports are the most obvious monetizable deliverable and are currently weak | Product | High | Medium | First |
| 5 | Replace `localStorage` token storage with a safer auth model | Current browser auth posture is weak for privileged actions | Frontend | High | Medium | First |
| 6 | Add frontend test coverage for login, dashboard, reports, opportunities, and platform control | Shipped UX has zero automated protection today | Frontend | High | Medium | First |
| 7 | Remove hidden nav entries for unshipped routes and kill dead product expectations | Hidden unfinished routes are feature-drift signals | Frontend | High | Low | First |
| 8 | Fix provider-configuration truth so local/provider/authority flows cannot appear available while being unusable | Defaults and runtime behavior currently contradict each other | Backend | High | Medium | First |
| 9 | Audit every tenant-facing module for synthetic or thin-provider behavior and label it honestly in UI | Prevents fake completeness | Product | High | Medium | First |
| 10 | Replace in-process observability snapshots with durable metrics/log/event reporting for real deployments | Current platform-state logic is too local to trust operationally | Infra | High | High | Second |
| 11 | Simplify the recommendation engine narrative until outcome quality materially improves | Current "intelligence" branding exceeds recommendation sophistication | Product | High | Low | Second |
| 12 | Harden the execution console around explicit approvals, previews, risk explanations, and rollback visibility | Automation must feel controlled, not magical | Product | High | Medium | Second |
| 13 | Consolidate CI so backend/frontend/preflight pipelines have one clear contract | Current workflow duplication adds noise and maintenance cost | DX | Medium | Medium | Second |
| 14 | Stop producing more architecture docs until product simplification decisions are made | The repo has too much analysis mass already | DX | Medium | Low | Second |
| 15 | Build one serious platform operator console instead of keeping table-based admin pages | Platform tooling is currently internal CRUD, not operator software | Frontend | Medium | Medium | Second |
| 16 | Add honest feature gating and UI messaging for provider-thin modules | Avoids broken expectations in local visibility, authority, and similar areas | Product | Medium | Medium | Second |
| 17 | Rework onboarding so it cleanly transitions into first-value workflow without sending users back into raw control forms | Current onboarding is better than nothing but not a closed loop | Product | Medium | Medium | Second |
| 18 | Make reporting storage and delivery production-grade instead of local filesystem oriented | Needed for white-label and operational trust | Backend | Medium | Medium | Third |
| 19 | Tighten local dev setup: one authoritative env strategy, one stack story, fewer warnings | Current DX is runnable but messy | DX | Medium | Medium | Third |
| 20 | Add frontend-side accessibility and responsive QA passes | Needed before any serious external use | Frontend | Medium | Medium | Third |
| 21 | Rationalize the database/model footprint against real shipped modules | Complexity cost is growing faster than product value | Backend | Medium | High | Third |
| 22 | Prove the WordPress execution path in production-like staging with telemetry and rollback drills | This is the most distinctive automation asset and needs hard evidence | Infra | Medium | High | Third |
| 23 | Build agency/portfolio UX only after tenant workflows are strong | Agency surface is premature right now | Product | Medium | Medium | Third |
| 24 | Establish a clear definition of launch that excludes synthetic, fixture-only, and spec-only capabilities | Prevents accidental self-deception during go-to-market | Product | Critical | Low | Always |
| 25 | Freeze backend breadth expansion for one cycle and pay down productization debt | The project should stop spreading and start finishing | Product | Critical | Medium | Always |
