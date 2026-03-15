# Claude Next Build Brief

## 1. Executive Summary

This repo is in the phase where Claude should stop expanding breadth and start converting existing backend capability into safer, more complete user workflows.

The current truth from the audits and codebase:
- The platform is backend-heavy and product-thin.
- The tenant UI is no longer a raw scaffold. It now has a coherent shell and six real buyer-facing product pages: dashboard, rankings, reports, opportunities, local visibility, and site health.
- Recent UI polish and execution-console work already happened. The next phase should extend those surfaces, not replace them.
- The backend already exposes a lot more than the frontend surfaces.
- The safest next phase is workflow closure, not new architecture.

Recommended build direction for Claude:
1. Finish execution inbox / approvals / rollback / audit UX on top of the existing opportunities page.
2. Finish report scheduling / delivery visibility on top of the existing reports page.
3. Add the competitors workflow as the next net-new tenant product page.
4. Add the citations workflow after competitors.
5. Defer broader content / authority / agency surfaces until those higher-value workflows are closed.

This brief is optimized for safe execution. Claude should work ticket-by-ticket, preserve working behavior, avoid broad rewrites, and stop if a slice requires risky backend changes.

## 2. What The Platform Is Today

Today the platform is:
- A usable tenant-facing local SEO operations workbench.
- A FastAPI backend with broad route coverage for campaigns, crawl, rankings, reports, intelligence, executions, competitors, citations, platform control, and provider health.
- A Next.js tenant UI with:
  - `/dashboard`
  - `/rankings`
  - `/reports`
  - `/opportunities`
  - `/local-visibility`
  - `/site-health`
- A thin but working platform control surface:
  - `/platform`
  - `/platform/orgs`
  - `/platform/orgs/[id]`
  - `/platform/providers`
  - `/platform/audit`

Current reality of key user flows:
- Onboarding exists and is one of the stronger productized flows.
- The dashboard still carries operator DNA and some manual controls, but the tenant shell is materially better than earlier audit states.
- The opportunities page already includes execution list/filter/detail/action behavior.
- The reports page already supports report list, detail, generation, and delivery.
- Competitors and citations have backend APIs but no tenant-facing workflow pages.

## 3. What The Platform Is Not Yet

It is not yet:
- A launch-ready non-technical-user product.
- A complete execution operations console.
- A finished reporting automation center.
- A real competitors product.
- A real citations product.
- A mature content/authority workspace.
- An agency-ready white-label platform.

Claude should not treat backend coverage as shipped product.

Specific non-truths to avoid reinforcing:
- Do not imply competitors are already shipped in the tenant UI.
- Do not imply citations are already a buyer workflow.
- Do not imply execution automation is fully trustable or autonomous.
- Do not imply report scheduling/delivery visibility is already complete in the tenant UI.
- Do not imply agency/portfolio workflows are ready for productization in this phase.

## 4. Current Stable Surfaces

These surfaces are currently stable enough that Claude should build on them, not redesign them:

- Tenant app shell and shared product components in `frontend/app/(product)/components/`
- Dashboard shell and onboarding flow in `frontend/app/(product)/dashboard/page.tsx`
- Rankings page in `frontend/app/(product)/rankings/page.tsx`
- Reports page in `frontend/app/(product)/reports/page.tsx`
- Opportunities page in `frontend/app/(product)/opportunities/page.tsx`
- Local visibility page in `frontend/app/(product)/local-visibility/page.tsx`
- Site health page in `frontend/app/(product)/site-health/page.tsx`
- Shared nav config in `frontend/app/(product)/nav.config.ts`
- Auth flow and API helper in:
  - `frontend/app/login/page.jsx`
  - `frontend/app/platform/api.js`

Stable backend surfaces Claude can rely on:
- Execution APIs in `backend/app/api/v1/executions.py`
- Reports APIs in `backend/app/api/v1/reports.py`
- Competitors APIs in `backend/app/api/v1/competitors.py`
- Citations APIs in `backend/app/api/v1/authority.py`
- Platform/provider health APIs already used by opportunities

## 5. Current Fragile Surfaces

These areas are fragile and should be extended carefully:

- `frontend/app/(product)/dashboard/page.tsx`
  - Still mixes briefing, setup, and manual operator actions.
- `frontend/app/platform/*`
  - Internal/admin tooling is functional but visually and structurally separate from the tenant product.
- Execution automation paths
  - Backed by real endpoints, but trust and safety UX is still incomplete.
- Reporting quality
  - Reports work, but output and automation visibility are still underbuilt.
- Provider-backed features
  - Backend breadth exceeds tenant UX and provider reality in several domains.
- Hidden future routes in nav config
  - `/settings`, `/locations`, `/competitors` are hidden stubs or incomplete surfaces.

Backend/runtime fragility Claude should respect:
- Avoid touching recommendation execution engine internals unless a UI slice cannot be completed without it.
- Avoid changing execution lifecycle semantics without proving no regression in existing opportunities behavior.
- Avoid changing report generation/delivery behavior unless the work is strictly needed for visibility/status surfacing.
- Avoid broad auth/session changes.

## 6. What Claude Must Preserve

Claude must preserve:
- Current working tenant routes and navigation behavior.
- Current onboarding flow and dashboard setup behavior.
- Current opportunities page behavior:
  - recommendation loading
  - execution loading/filtering
  - dry-run preview behavior
  - execution action buttons already in place
  - WordPress execution setup visibility
- Current reports page behavior:
  - report list/detail loading
  - generate report
  - deliver report
- Current local visibility and site health pages.
- Current platform admin pages.
- Existing backend API contracts wherever possible.
- Current build health and CI-green assumptions.

Preservation rules:
- Prefer additive UI slices over route rewrites.
- Prefer extension of current pages over creating replacement pages.
- Do not refactor shared shell/components unless the ticket requires a small local extension.
- Do not reorganize the backend architecture during this phase.

## 7. What Claude Should Build Next

Claude should build the next phase in this order:

### Phase target
**Workflow Closure Phase: Execution + Reporting + Competitors + Citations**

### Why this phase
- It uses existing backend leverage.
- It strengthens current user-visible surfaces instead of inventing new ones.
- It closes the gap between recommendation, execution, reporting, and audit.
- It adds commercially meaningful tenant workflows before broader surfaces like content/authority/agency.

### Concrete next-build goals

1. Execution inbox and audit completion inside the opportunities surface
- Make the opportunities page a complete human-in-the-loop action center.
- Improve visibility of approval state, mutation count, errors, result summaries, and rollback history.
- Add clearer audit/timeline visibility using existing execution and automation data.

2. Report scheduling and delivery visibility inside the reports surface
- Surface schedule state, cadence, next run, retry count, failure state, and delivery history.
- Make reporting feel operationally managed, not just manually generated.

3. Competitors workflow as the next tenant product page
- Add nav exposure only when the page is usable.
- Support add/list/snapshot/gaps with clear empty/error/provider-thin states.

4. Citations workflow as the next tenant product page or subordinate local SEO workflow
- Support submission and status visibility.
- Keep scope tight and local-SEO-centered.

Only after those are complete:
- content / topical authority
- backlinks / outreach
- broader WordPress provisioning UX
- agency / portfolio productization

## 8. What Claude Must Not Touch Yet

Claude must not touch these areas in this phase unless a ticket explicitly requires a minimal local change:

- Auth architecture and token strategy
- Global navigation redesign
- Dashboard rewrite
- Platform/admin app rewrite
- Execution engine internals in `backend/app/intelligence/recommendation_execution_engine.py`
- WordPress execution transport/plugin behavior
- Core provider credentials architecture
- Report rendering engine internals beyond exposing status/visibility data
- Org/tenant/role model
- Broad CSS/design system rewrite
- Agency/portfolio/multi-location product surfaces

Do not start:
- content workspace
- authority/backlinks workspace
- agency console
- major dashboard simplification
- reporting artifact redesign

Those are later phases.

## 9. Recommended Next Build Phase

Recommended next build phase:

**Phase: Workflow Closure 1**

Definition:
- Complete the current opportunities page into a trustworthy execution inbox.
- Complete the current reports page into a manageable reporting automation center.
- Add the first two backend-rich, UI-missing tenant workflows:
  - competitors
  - citations

Success condition for this phase:
- A tenant user can:
  - review recommendations
  - inspect execution state
  - approve/reject/run/retry/cancel/rollback safely
  - understand execution history and current blockers
  - manage report schedule and see delivery state
  - use a competitors page
  - use a citations page

Non-goals:
- Do not broaden into content, authority, outreach, or agency productization.
- Do not attempt major intelligence-quality improvements.
- Do not attempt broad automation hardening beyond UI-safe visibility and gating.

## 10. Exact Ticket Order For Claude

Claude should implement tickets in this exact order.

### T1. Execution Inbox Completion
Scope:
- Extend `frontend/app/(product)/opportunities/page.tsx`
- Improve execution list/detail visibility
- Expose approval state, mutation count, last error, result summary, rollback state more clearly

Why first:
- This page already has real execution behavior.
- This is the shortest path to workflow closure without introducing new routes.

Backend changes allowed:
- Small additive response-field exposure only if needed.

Stop condition:
- If the ticket requires changing execution state-machine behavior, stop and document the blocker.

### T2. Execution Audit / Timeline Visibility
Scope:
- Add visible execution-history / recommendation-history timeline in opportunities
- Reuse existing execution detail plus automation timeline data if possible

Why second:
- Users need trust and traceability after actions are exposed.

Backend changes allowed:
- Small additive read endpoints or payload enrichment only.

Stop condition:
- If timeline assembly requires event model redesign, stop.

### T3. Report Schedule Editor
Scope:
- Extend `frontend/app/(product)/reports/page.tsx`
- Add schedule fetch/edit/save UI using `/reports/schedule`
- Show enabled state, cadence, timezone, next run, retry count

Why third:
- Existing backend exists and current page is already a natural host.

### T4. Report Delivery Visibility
Scope:
- Extend reports page with status summary and delivery history visibility
- Clarify generated vs delivered vs failed

Why fourth:
- Makes reports operationally trustworthy.

Backend changes allowed:
- Add read-only delivery-history exposure if not already returned.

Stop condition:
- If it requires report artifact model rewrite, stop.

### T5. Competitors Page
Scope:
- Add `frontend/app/(product)/competitors/page.tsx`
- Make competitors nav item visible only when page is shipped
- Support add/list/snapshots/gaps

Why fifth:
- High commercial value, backend already exists, no current tenant page.

Rules:
- Keep the page consistent with current product shell/components.
- Handle empty/provider-thin states honestly.

### T6. Citations Page or Local SEO Extension
Scope:
- Add `frontend/app/(product)/citations/page.tsx` or a tightly scoped citations workflow linked from local visibility
- Support submission and status tracking

Why sixth:
- Strong local SEO value with existing backend support.

Rules:
- Keep the workflow small and legible.
- Do not broaden into backlinks/outreach.

### T7. Integration Polish
Scope:
- Link opportunities, reports, competitors, and citations workflows together where needed
- Add minimal cross-page CTAs
- Remove any remaining hidden-nav mismatch introduced by the new pages

Why last:
- Only after core slices are working.

## 11. Safe Implementation Rules

Claude must follow these rules:

1. Work ticket-by-ticket.
2. Make additive changes first.
3. Reuse existing shared components and patterns.
4. Preserve current route structure unless a ticket explicitly adds one new page.
5. Prefer frontend work over backend rewrites.
6. Only make backend changes when:
   - the required data is not currently exposed
   - the change is additive
   - the change does not alter core lifecycle semantics
7. Do not change execution or reporting behavior just to make the UI easier.
8. Do not touch unrelated pages while implementing a ticket.
9. Keep copy honest:
   - do not overstate automation
   - do not pretend provider-thin states are real completion
10. Document before large code changes if a ticket unexpectedly expands.

## 12. Validation Requirements

After each ticket or logical slice, Claude must validate:

- frontend lint passes
- frontend build passes
- affected page loads without runtime crash
- affected user flow works against current local APIs
- no existing tenant route regresses:
  - `/dashboard`
  - `/rankings`
  - `/reports`
  - `/opportunities`
  - `/local-visibility`
  - `/site-health`

Ticket-specific validation:

- Execution tickets:
  - execution list loads
  - pending/completed/failed states render
  - dry-run path still works
  - approve/reject/run/retry/cancel/rollback UI behavior still works

- Report tickets:
  - report list/detail still loads
  - generate still works
  - deliver still works
  - schedule load/save works

- Competitors ticket:
  - add competitor works
  - list works
  - snapshots and gaps render without crash
  - empty state is understandable

- Citations ticket:
  - submission works
  - status list works
  - no-data state is understandable

## 13. Merge / Regression Rules

Claude should only consider a ticket merge-ready if:

- The ticket is scoped and complete.
- Existing working flows still behave the same or better.
- No broad refactor was introduced.
- No backend lifecycle semantics were changed unintentionally.
- New UI follows the existing product shell and design language.
- New routes are only added when they are usable on day one.
- Hidden nav items are only made visible when the corresponding route is actually ready.

Regression red flags that must block merge:
- Dashboard setup flow breaks.
- Opportunities action flow regresses.
- Reports generate/deliver flow regresses.
- New page depends on speculative backend changes.
- New UI exposes backend-only states without clear copy.
- A ticket turns into a rewrite.

## 14. Final Claude Prompt

Use this prompt as the next Claude instruction package:

```text
Work in this WSL project path:
/home/verixlabs/SEO Accelerator Tool

Use these documents as your primary brief:
- docs/claude-next-build-brief.md
- docs/master-system-audit.md
- docs/full-feature-fulfillment-audit.md
- docs/post-ui-feature-fulfillment-ticket-backlog.md
- docs/claude-ui-validation-and-polish-sweep.md

Your assignment:
Implement the next safe build phase: Workflow Closure 1.

Phase goals:
1. Complete the opportunities page into a trustworthy execution inbox and audit surface.
2. Complete the reports page into a report scheduling and delivery visibility center.
3. Add the competitors tenant workflow.
4. Add the citations tenant workflow.

Important constraints:
- Work ticket-by-ticket in the order defined in docs/claude-next-build-brief.md.
- Preserve all currently working behavior.
- Do not do broad rewrites.
- Do not redesign the dashboard or platform admin areas in this phase.
- Prefer additive UI work on top of existing routes and components.
- Avoid risky backend changes unless absolutely necessary.
- If a ticket requires changing execution engine semantics, reporting engine semantics, auth architecture, or provider credential architecture, stop and document the blocker instead of pushing through.
- Keep product copy honest. Do not overstate automation or backend-only capability.
- Reuse existing product shell/components and current visual language.

Validation rules:
- Validate after each ticket or logical slice.
- Run frontend lint and frontend build after each slice.
- Verify affected flows manually against the current local app when possible.
- Confirm no regressions on:
  - /dashboard
  - /rankings
  - /reports
  - /opportunities
  - /local-visibility
  - /site-health

Execution rules:
- Before making large or risky changes, write a short implementation note in docs if needed.
- Keep changes tightly scoped to the active ticket.
- Do not start later-phase work early.

Start with:
T1. Execution Inbox Completion

Then continue ticket-by-ticket only if the current ticket is stable and validated.
```
