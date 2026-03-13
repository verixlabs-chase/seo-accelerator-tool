# UI/UX Productization Plan

**Project:** SEO Accelerator Tool (InsightOS)
**Role:** Product / UX Strategy
**Status:** Pre-launch recovery planning
**Date:** 2026-03-13
**Based on:** Codex audit findings + codebase exploration

---

## 1. Executive Summary

The product has real backend infrastructure — crawling, rank tracking, reporting, intelligence, recommendations, onboarding orchestration — but the customer-facing tenant UI is effectively one screen. That screen (`/dashboard`, `dashboard/page.tsx`, 1216 lines) is overloaded with raw operational forms built for internal operators, not for business owners. Eight of the nine sidebar navigation items are disabled. CTAs are visually present but functionally inert. The first-run experience does not exist.

The risk is not missing technology. The risk is that a real customer lands on this product and cannot figure out what to do, what has happened, or why it matters to them.

This plan defines how to recover that UX without rewriting the app, without breaking existing working flows, and without requiring large backend changes.

**Goal:** Make the product usable and trustworthy for a non-technical home-service business owner within a single focused sprint, using additive changes and hiding/disabling patterns rather than destructive rewrites.

---

## 2. Current UX Reality

| Layer | Status |
|---|---|
| Visual design system | Good. Dark theme, tokens, components are solid. |
| Component library | Present. 18 components in `(product)/components/`. Several are inert. |
| Tenant page routes | 1 real route (`/dashboard`). All others are `disabled` in nav. |
| Navigation | 9 items defined in `dashboard/page.tsx:30`. 8 are disabled with "Coming soon". |
| Dashboard | 1216-line single page with 4 raw forms: campaign create, crawl, rank, report. |
| AppShell | Sidebar hidden below `xl` breakpoint. No mobile nav exists. |
| API client | `platform/api.js` wraps auth + refresh. Dashboard uses its own inline fetch pattern. |
| Backend APIs | 35 modules, 100+ endpoints. Frontend calls a small subset. |
| Guidance/CTAs | `InsightCard.tsx:33` action buttons are inert. `EmptyState.tsx:23` CTA is inert. |
| Search | `TopBar.tsx:25` is static placeholder text. |
| Intelligence | Exists in backend (`intelligence.py`, `recommendations.py`). Not surfaced in UI. |
| Reporting | Backend supports generate/list/get/schedule/deliver. Frontend exposes only two buttons on dashboard. |

---

## 3. Why the Current Product Is Confusing for Non-Technical Users

### 3.1 The dashboard speaks operator language
The forms on the dashboard use terms like: "Crawl Type", "Cluster Name", "Location Code", "Month Number", "Seed URL". A home-service business owner does not know what any of these mean. There is no explanation, no tooltip, no plain-English label, and no consequence description for making a wrong choice.

### 3.2 The sequence is invisible
The correct workflow is: create campaign → run crawl → run rank snapshot → generate report. This sequence is not communicated anywhere. The forms sit side by side with no indication that order matters. A user could try to generate a report before creating a campaign and get an error with no explanation.

### 3.3 The nav promises what doesn't exist
The sidebar shows Locations, Rankings, Local Visibility, Site Health, Competitors, Opportunities, Reports, and Settings. All are disabled. A new user will click each one, see nothing, and conclude the product is broken or incomplete. This creates immediate distrust.

### 3.4 CTAs do nothing
`InsightCard` shows action buttons. `EmptyState` shows a CTA button. Neither does anything (`onClick` is not wired). A user who clicks these gets no response — not even an error — which feels like a broken product.

### 3.5 The dashboard does not answer the right questions
A business owner's mental model is: "Is my business showing up online? Is it getting better or worse? What should I do today?" The current dashboard answers this partially — KPI cards and charts exist — but the action layer is disconnected from the intelligence layer. The "what to do next" answer is absent or generic.

### 3.6 No first-run experience
A new user who has never used this product will land on the dashboard, see empty KPI cards (or pre-filled charts if demo data exists), and face a blank campaign selector. There is no step-by-step flow to get from "just logged in" to "my data is set up." The onboarding APIs exist in `onboarding.py` and `onboarding_service.py` but are not connected to the UI at all.

---

## 4. Launch-Critical UX Problems

These are problems that will cause user confusion or loss of trust on first contact. They must be fixed before showing this product to real customers.

| # | Problem | Severity | Current Location |
|---|---|---|---|
| 1 | 8 of 9 nav items are dead ends | Critical | `dashboard/page.tsx:30`, `SidebarNav.tsx:43` |
| 2 | No first-run / onboarding flow | Critical | Missing entirely |
| 3 | Dashboard forms use raw operator language | Critical | `dashboard/page.tsx:991` |
| 4 | Inert CTAs (InsightCard, EmptyState) | High | `InsightCard.tsx:33`, `EmptyState.tsx:23` |
| 5 | No mobile/tablet navigation | High | `AppShell.tsx:29` |
| 6 | Dashboard does not explain workflow sequence | High | `dashboard/page.tsx` |
| 7 | Static search with no behavior | Medium | `TopBar.tsx:25` |
| 8 | Reports buried on dashboard with no context | Medium | `dashboard/page.tsx` |
| 9 | Intelligence/recommendations not surfaced | Medium | Backend exists, no UI |
| 10 | No empty state explanation for new users | Medium | `EmptyState.tsx` |

---

## 5. Product Promise vs Actual Feature Availability

| Nav Item | Promise | Reality | Recommended Action |
|---|---|---|---|
| Dashboard | Full operational view | Overloaded with raw forms | Redesign surface, keep data |
| Locations | Location management | Backend exists, no UI | Hide until built |
| Rankings | Rankings view | Data exists, no dedicated page | Build lightweight page — high priority |
| Local Visibility | Visibility map/trends | Partial data on dashboard | Hide or link to dashboard section |
| Site Health | Site issue tracking | Badge shows "3" but route is absent | Hide until built |
| Competitors | Competitor tracking | Backend exists, no UI | Hide until built |
| Opportunities | Action center | Recommendations exist in backend, no UI | Build lightweight version — high priority |
| Reports | Report center | Backend full, UI is 2 dashboard buttons | Build dedicated page — high priority |
| Settings | Account/profile settings | Missing entirely | Build minimal version — medium priority |

---

## 6. Safe UX Recovery Strategy

The core principle: **add and reveal, don't rewrite and replace.**

### 6.1 Strategy summary

1. **Remove dead-end nav items from sight** (disable or hide, not delete) — immediate trust fix
2. **Redesign the dashboard surface** to answer the three user questions: what changed, why it matters, what to do next — keep all existing data/API calls, change the layout and copy
3. **Build a first-run flow** using the existing `onboarding.py` API and a simple multi-step component — additive, not destructive
4. **Wire up inert CTAs** with real behavior (modals, drawers, navigation) — no backend change required
5. **Add three lightweight pages** (Rankings, Reports, Opportunities) using existing backend APIs — additive routes
6. **Add a mobile nav fallback** using a drawer pattern — additive, does not change desktop layout

### 6.2 What this strategy avoids

- Does not restructure the Next.js app router
- Does not change any backend API contracts
- Does not remove any existing working dashboard functionality
- Does not require new state management libraries
- Does not require database migrations
- Does not require touching platform/admin routes

---

## 7. What Should Be Fixed First vs Deferred

### Fix First (P0 — before any customer sees this)

- Hide disabled nav items that have no timeline (or replace with "Coming soon" badge that is clearly a badge, not a nav destination)
- Redesign dashboard layout to reduce raw form exposure
- Add plain-English labels to all existing form fields
- Wire EmptyState and InsightCard CTAs to something real (even a modal or a scroll-to)
- Add a "start here" prompt for zero-state users

### Fix Second (P1 — before soft launch)

- Build first-run onboarding flow (3-step wizard: name your business, connect your website, run first check)
- Build Rankings page using existing `/rank/trends` and `/rank/snapshots` APIs
- Build Reports Center using existing `/reports` APIs
- Build Opportunities/Action Center using existing `/recommendations` APIs
- Add mobile navigation drawer

### Defer (P2 — post-launch)

- Site Health page (backend incomplete, UX complex)
- Competitors page (requires UX design for competitive comparison)
- Locations management page (requires hierarchy UX design)
- Settings (minimal version P1, full version P2)
- TopBar search (requires indexing strategy)
- Portfolio/Agency views (separate product surface)

---

## 8. UX Principles for This Product

These principles should govern every decision during recovery and ongoing development.

1. **Answer the three questions first.** Every dashboard state should answer: what changed, why it matters, what to do next. If a surface can't answer at least one of these, it shouldn't ship.

2. **No dead ends.** Every button, every link, every CTA must do something. If a feature isn't ready, hide the button. Do not ship inert UI elements.

3. **No jargon without translation.** Every SEO term must have a plain-English equivalent in the UI. "Keyword rankings" = "how high you show up when customers search." Never use internal system terms (cluster, crawl type, location code) in customer-facing copy.

4. **Show the next step.** At every point in the product, the user should be able to see what to do next. If they've completed setup, show the first insight. If they've seen insights, show recommended actions. The product should always be moving them forward.

5. **Trust through transparency.** Show when data was last updated. Show when a job is running. Show when something failed and why. Silence is worse than bad news.

6. **Additive over destructive.** When making changes: add first, hide second, remove last. Never remove a working feature without a clear replacement.

7. **Mobile-first navigation, desktop-first content.** The sidebar layout works for content-heavy desktop views. Mobile users need navigation, not content density. Solve navigation separately from layout.

8. **Intelligence should lead, not follow.** If the backend knows a recommendation exists, surface it. Do not make the user go find the recommendation section. The system should push insight to the surface.

---

## 9. Recommended Navigation Strategy

### 9.1 Immediate change (no code refactor needed)

Remove these items from the sidebar entirely (or make them visually distinct "roadmap" items that are not clickable):

- Locations
- Local Visibility
- Site Health
- Competitors

These have no usable tenant UI and showing them as navigable creates confusion.

### 9.2 Keep but fix

- **Dashboard** — keep as primary surface, redesign layout
- **Rankings** — keep in nav, build lightweight page
- **Opportunities** — keep in nav, build lightweight page
- **Reports** — keep in nav, build lightweight page
- **Settings** — keep in nav, build minimal page

### 9.3 Nav item count

A sidebar with 5 real destinations is better than a sidebar with 9 dead ends. Reduce to what exists. Add back as pages are built.

### 9.4 Recommended final nav shape (current sprint)

```
Dashboard       (active)
Rankings        (active after P1)
Reports         (active after P1)
Opportunities   (active after P1)
Settings        (minimal after P1)
```

### 9.5 Nav item definition location

Currently defined inline in `dashboard/page.tsx:30`. This should eventually move to a shared config file (e.g., `(product)/nav.config.ts`) so nav state is managed centrally. This is a P2 engineering change — do not block UX work on it.

---

## 10. Recommended Dashboard Strategy

### 10.1 The dashboard should be a daily briefing, not a control panel

Current: 4 operator forms, KPI cards, charts, timeline.
Recommended: KPI summary, top insight, ranking movement summary, one recommended action, quick-access to reports.

### 10.2 Sections to keep (existing data)

- KPI cards (keep, relabel in plain English)
- Visibility trend chart (keep)
- Ranking trend chart (keep)
- Timeline/execution feed (keep, relabel as "Recent activity")
- Campaign selector (keep, simplify)

### 10.3 Sections to restructure

- Move crawl/rank/report forms off the main dashboard surface. Replace with an "Actions" panel or move to a dedicated "Run" drawer. The forms don't need to be deleted — they need to be de-emphasized and contextualized.
- Replace raw form labels with plain-English equivalents.
- Promote `ActionDrawer` content to be intelligence-driven using existing `/campaigns/{id}/dashboard` and recommendation data.

### 10.4 Dashboard answer checklist

| Question | Current answer | Target answer |
|---|---|---|
| What changed? | Charts show trends. KPI numbers visible. | Add delta indicators: "+3 ranking positions this week" |
| Why it matters? | Insight cards present but generic | Wire to campaign intelligence: "Your top keyword moved from #12 to #9" |
| What to do next? | ActionDrawer present but generic | Wire to recommendations API: "You have 2 opportunities to improve site speed" |

---

## 11. Recommended First-Run Experience

### 11.1 Trigger condition

When a user logs in and has no campaign (`campaigns` list is empty), show the onboarding flow instead of the main dashboard.

### 11.2 Flow steps (3 steps maximum)

**Step 1: Name your business**
- "What's your business called?" → Campaign name
- "What's your website?" → Domain input (currently called "seed URL" — rename this)
- Plain language: "We'll use this to check how your business shows up online"

**Step 2: Tell us your focus area**
- "What type of work do you do?" → maps to keyword/cluster (abstract the SEO concept)
- "What city or area do you serve?" → maps to location code (show a city dropdown or text field, not a raw code)

**Step 3: Run your first check**
- "We're running your first website scan now" → triggers crawl + rank snapshot in background
- Show a progress indicator
- "We'll have your first results in a few minutes"

### 11.3 Implementation approach

- Use existing `POST /campaigns` to create the campaign
- Use existing `POST /crawl/schedule` for the crawl
- Use existing `POST /rank/schedule` for the rank snapshot
- Use existing `POST /auth/me` to detect first-time user state
- New: A 3-step wizard component (no new backend APIs required)
- New: A route or modal state that renders instead of dashboard when campaign count is 0

### 11.4 Backend onboarding APIs

`onboarding.py` and `onboarding_service.py` exist. Review whether `POST /onboarding` can orchestrate steps 2-3 before building custom orchestration in the frontend. If it can, use it. If its contract is unclear, use direct campaign/crawl/rank calls to avoid dependency on an untested flow.

---

## 12. Recommended Reporting Experience

### 12.1 Current state

Backend: `reports.py` supports generate, list, get, schedule, deliver.
Frontend: Two buttons on the dashboard ("Generate Report", "Deliver Latest").

### 12.2 What's needed

A dedicated `/reports` page that:
- Lists all reports for the selected campaign
- Shows report status (generated, pending, delivered)
- Allows the user to generate a new report in plain language ("Create this month's report")
- Allows the user to preview a report
- Allows the user to deliver a report (send to email)
- Shows scheduled report cadence

### 12.3 Implementation approach

- All data comes from existing `/reports` APIs — no backend changes
- New frontend route: `/reports` using `(product)` route group
- Use existing `ReportPreview.tsx` component for report display
- Remove "Generate Report" and "Deliver Latest" from dashboard, or keep as quick-access shortcuts that link to the reports page

### 12.4 Plain-English copy guidance

| Current label | Replace with |
|---|---|
| "Generate Report" | "Create this month's report" |
| "Deliver Latest" | "Send report to email" |
| "Month Number" | "Which month?" (dropdown: January, February...) |
| "Recipient Email" | "Send to" |

---

## 13. Recommended Action Center Experience

### 13.1 Current state

`recommendations.py` exists in backend. No tenant-facing action center exists. The sidebar shows "Opportunities" with a badge count of "5" but the route does nothing.

### 13.2 What's needed

A lightweight `/opportunities` page that:
- Lists recommendations from the backend
- Each recommendation shows: what the issue is (plain English), why it matters, what action to take
- Allows the user to mark an action as "done" or "snooze" (or at minimum, to acknowledge it)
- Shows a count badge in the nav that matches the number of open recommendations

### 13.3 Implementation approach

- Use existing `GET /recommendations` endpoint
- New frontend route: `/opportunities` using `(product)` route group
- Use `InsightCard.tsx` component (already built) — wire up its action buttons
- Badge count in `SidebarNav` should be driven by the real recommendation count, not hardcoded "5"

### 13.4 Interaction model

Each recommendation card shows:
- Title (plain English): "Your homepage loads slowly"
- Impact: "Slow pages rank lower in search results"
- Action: "View details" (links to relevant section) or "Mark as reviewed"

Avoid complex approve/run workflows in P1. Acknowledge + link is enough to make it functional.

---

## 14. Mobile/Tablet UX Gaps

### 14.1 Current state

`AppShell.tsx:29` hides the sidebar below the `xl` breakpoint (`xl:block`). There is no alternate navigation for mobile or tablet viewports. A user on a phone or tablet has no way to navigate between sections.

### 14.2 Impact

Most SMB business owners check tools on mobile. A missing mobile nav is a launch-blocking issue for the target user persona.

### 14.3 Recommended solution

Add a mobile navigation drawer that:
- Appears as a hamburger menu button in the TopBar on viewports below `xl`
- Opens a slide-in drawer containing the same nav items as the sidebar
- Does not require changes to the desktop layout
- Reuses `SidebarNav.tsx` inside the drawer

### 14.4 Implementation approach

- Add a `MobileNav.tsx` component with a drawer/sheet pattern
- Add hamburger button to `TopBar.tsx` (visible only below `xl`)
- Pass the same `navItems` prop used in `AppShell.tsx`
- No routing or data changes required

---

## 15. Safe Incremental Rollout Plan

The following sequence minimizes regression risk and allows each change to be tested independently.

### Sprint 1 — UX triage (no new pages, no new APIs)

1. Hide unready nav items from the sidebar (Locations, Local Visibility, Site Health, Competitors). Do not delete — comment in nav config or add `hidden: true` flag to nav item type.
2. Relabel all dashboard form fields with plain-English labels (copy change only).
3. Wire `EmptyState.tsx` CTA to trigger the campaign creation form (scroll or open modal — no new API).
4. Wire `InsightCard.tsx` action buttons to relevant sections (scroll-to or navigate — no new API).
5. Add a zero-state detection on dashboard: if `campaigns.length === 0`, show an intro prompt instead of empty KPI cards.

### Sprint 2 — First-run flow

6. Build 3-step onboarding wizard component (new component, additive).
7. Connect to existing `POST /campaigns`, `POST /crawl/schedule`, `POST /rank/schedule`.
8. Show wizard when campaign count is 0, redirect to dashboard when complete.

### Sprint 3 — Core pages (additive routes)

9. Build `/reports` page using existing `GET /reports` and `POST /reports/generate`.
10. Build `/opportunities` page using existing `GET /recommendations`.
11. Build `/rankings` page using existing `GET /rank/trends` and `GET /rank/snapshots`.

### Sprint 4 — Mobile + polish

12. Add `MobileNav.tsx` drawer component.
13. Update `TopBar.tsx` to show hamburger button on mobile.
14. Wire recommendation count badge to real API data.
15. Build minimal `/settings` page.

---

## 16. Regression Risks to Avoid

| Risk | Description | Mitigation |
|---|---|---|
| Breaking campaign data fetch | Dashboard depends on inline fetch logic for campaigns. Any restructuring risks breaking this. | Do not touch fetch logic in Sprint 1. Only change copy/layout. |
| Breaking auth flow | Token refresh logic exists in both `platform/api.js` and inline in `dashboard/page.tsx`. These two patterns can diverge. | Do not consolidate fetch clients until explicit refactor sprint. |
| Breaking chart data | `VisibilityTrendChart` and `RankingTrendChart` are fed from dashboard state. Reordering JSX can break data binding. | Keep chart components in place, only add/remove surrounding layout. |
| Nav item removal | If nav items are deleted (not hidden), any user with a bookmark to a future route will get a 404. | Hide with `hidden: true` or `disabled: true` — never delete the item from config. |
| Breaking platform routes | `/platform/**` routes are separate from product routes. Do not touch these during product UX work. | Treat `app/platform/**` as out of scope for all tenant UX work. |
| Onboarding API contract | `onboarding.py` may have assumptions about call order. If orchestration fails silently, users will be stuck. | Use individual campaign/crawl/rank API calls for the wizard rather than the orchestration endpoint until it is explicitly tested. |

---

## 17. P0 / P1 / P2 Priorities

### P0 — Must fix before any customer sees this

- [ ] Hide dead-end nav items
- [ ] Relabel form fields in plain English
- [ ] Wire inert CTAs to real behavior (even scroll-to or modal)
- [ ] Add zero-state / first-time user prompt on dashboard
- [ ] Confirm that "Generate Report" and "Deliver Latest" work end-to-end with real data

### P1 — Must ship before soft launch

- [ ] 3-step onboarding wizard (first-run flow)
- [ ] `/reports` page
- [ ] `/opportunities` page
- [ ] `/rankings` page
- [ ] Mobile navigation drawer
- [ ] Minimal `/settings` page
- [ ] Recommendation badge count driven by real data

### P2 — Target for post-launch iteration

- [ ] `/site-health` page
- [ ] `/competitors` page
- [ ] `/locations` page
- [ ] TopBar search functionality
- [ ] Intelligence-driven daily summary on dashboard
- [ ] Scheduled reporting UI
- [ ] Auto-suggested keywords in onboarding
- [ ] Portfolio/agency view
- [ ] Consolidate API client patterns (engineering refactor)
- [ ] Fix backend test execution (cwd-independent, timeout fixes)
- [ ] Re-enable build-time lint enforcement

---

## 18. Definition of Launch-Ready UX

The product is launch-ready when a non-technical home-service business owner can:

1. Log in for the first time and immediately understand what to do next
2. Complete a setup flow without encountering any SEO jargon they cannot understand
3. See their first data results within a reasonable wait time with a progress indicator
4. Navigate to Rankings, Reports, and Opportunities without hitting dead ends
5. Generate and receive a report by email
6. Return the next day and see what changed since their last visit
7. Know what to do next at every point in the product
8. Use the product on a phone or tablet without losing navigation

Every disabled nav item that remains visible is a launch blocker. Every inert CTA that ships is a trust-erosion event. Every raw operator term in the customer-facing UI is a comprehension failure.

---

## Recommended Next Implementation Sequence

This is the safest order to implement changes without breaking working functionality:

**Step 1 (no risk):** Copy and label changes only. Rename form fields. Update button text. No functional code changes.

**Step 2 (low risk):** Hide nav items. Add `hidden: true` to nav item type and filter in `SidebarNav.tsx`. No routing changes. No API changes.

**Step 3 (low risk):** Wire existing inert CTAs. `InsightCard` and `EmptyState` buttons get `onClick` handlers that scroll, open modals, or navigate to existing sections. No new API calls.

**Step 4 (low risk):** Add zero-state detection on dashboard. Read `campaigns.length` (already fetched) and conditionally render an intro prompt. No new API calls.

**Step 5 (medium risk):** Build onboarding wizard as a new component that is only shown when `campaigns.length === 0`. Uses existing API calls. Does not touch existing dashboard code paths.

**Step 6 (medium risk):** Add new page routes (`/reports`, `/opportunities`, `/rankings`) under the `(product)` route group. Each is additive — a new file, new API calls using `platformApi`, new component. Does not touch dashboard code.

**Step 7 (low risk):** Add `MobileNav.tsx` and update `TopBar.tsx` with hamburger button. Pure addition — does not modify desktop layout or any data fetching.

**Step 8 (medium risk):** Wire nav badge counts to real API data. Replace hardcoded `"5"` in Opportunities badge with live recommendation count.
