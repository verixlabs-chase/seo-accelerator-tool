# UI/UX Productization Plan

**Project:** SEO Accelerator Tool (InsightOS)
**Role:** Product / UX Strategy
**Status:** Historical recovery plan plus active follow-on sprints
**Date:** 2026-03-13
**Reconciled:** 2026-07-28
**Based on:** Codex audit findings + codebase exploration

---

> **Current status (2026-08-04):** Customer UX Sprints UX1-UX9 created the
> working baseline. Customer screenshot review found that the interface still
> has dense operations-console patterns, repeated status content, technical
> copy, weak visual hierarchy, and too little decision-useful visualization.
> UX10-UX12, I1.4/T27 measurement readiness, and I1.2/T28 evidence-backed
> forecasting, the bounded I1.3 daily action brief, and evidence-based location
> questions and governed drafting are now complete. **MKT1.1 automated local
> keyword discovery is now in progress**: its first slices add a location-aware
> Find Searches page, real demand visualization, owner-friendly opportunity
> groups, confirmed service and service-area setup, explicit excluded markets,
> a bounded AI action for sorting only unclear phrases, and direct promotion
> into Search Rankings. Owners can now correct a phrase in place, attach it to
> a confirmed service, hide it as irrelevant, undo that choice, and have the
> scoped decision reused on later refreshes. Saved competitor domains now add
> clearly labeled competitor opportunities with the competing page and
> observed position, without presenting that position as the customer's own
> result or bypassing the same service and service-area checks. The follow-on
> **I1.4/T29 measured action-value
> sprint** is scheduled after G1.4 supplies live Google Business Profile
> performance data; it adds separate Website and Google Profile action lanes
> with real baselines and measured results. A later **ENG1 verified-progress
> sprint** adds evidence-backed milestones and badges after those measurement,
> analytics, onboarding, and paid-beta foundations are operating. The
> authoritative execution brief is
> [claude-next-build-brief.md](./claude-next-build-brief.md).
> A later **UX13 natural product voice and comprehension sprint** now covers
> the remaining gap between technically simple copy and language that sounds
> natural when a service-business owner reads it aloud. It includes public,
> onboarding, product, report, notification, and AI-generated copy.
>
> **Sprint 9 language standard:** Design and write for an owner or manager of a service-based
> business. Customer-facing screens must explain business meaning first and retain SEO,
> provider, and system terminology only as optional supporting detail.
>
> **Handoff after UX9:** Follow the reconciled execution order in
> [claude-next-build-brief.md](./claude-next-build-brief.md#recommended-execution-order-from-the-current-state).
> It now coordinates production trust (TR1), automated data (G1), live and AI-assisted
> intelligence (I1), data trust (DT1), premium reports (RPT1), alerts (ALT1), guided onboarding (CX1),
> research/content/authority (MKT1/CNT1/AUTH1), safe WordPress automation (WP1), switching/imports
> (MIG1), product analytics (PA1), privacy/portability (GOV1), advanced search coverage
> (SEO2), outcome learning (I2), AI visibility (AIV1), multi-location (ML1), commerce
> (COM1), launch operations (OPS1), and enterprise delivery (ENT1). Call tracking, CRM,
> job-management, booked-job, payment, revenue, and sales-attribution connections remain
> explicitly excluded until separately approved.
>
> **Planned allowance and value UX:** G1.3A replaces customer-visible monthly
> provider dollars with plain `Insight Credits`, while the internal cost ledger
> continues to protect the 85% software-usage margin. VAL1 then rebuilds Search
> Value around current location-specific market research and measured Search
> Console behavior, with an auditable range, confidence, source dates, and no
> revenue claim. Their governing scope and acceptance criteria live in the
> authoritative execution brief.

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

   Sprint 9 vocabulary:
   - `Rankings` becomes `Search Rankings`.
   - `Local Visibility` becomes `Local Search`.
   - `Site Health` becomes `Website Health`.
   - `Opportunities` becomes `Next Steps`.
   - `Citations` becomes `Directory Listings`.
   - `Organic Value` becomes `Search Value`.
   - `Runtime truth` becomes `How current is this information?`.
   - `Intelligence cycle` becomes `Check for new recommendations`.
   - `Provider-backed` is explained as information from a connected live data service.

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

### Sprint 5 — Location context and information architecture

16. Add a persistent `Viewing: All locations / [location]` selector to the shared authenticated shell.
17. Preserve the selected location across product-page navigation.
18. Make page scope explicit in the title area of every location-sensitive page.
19. Make Rankings portfolio rows switch directly to the selected location.
20. Separate `All locations` comparison from individual-location detail.
21. Reduce the primary navigation to core workflows and move secondary tools under More.
22. Rename ambiguous refresh actions so reloading, checking status, and running paid provider checks cannot be confused.

### Sprint 6 — Rankings and Site Health comprehension

23. Restructure Rankings into explicit portfolio and individual-location modes.
24. Put the location switcher, strongest phrase, weakest phrase, latest check, and live-check action above the fold.
25. Rewrite ranking summaries in plain language before showing charts and technical metadata.
25a. Add visual portfolio comparison, current-position distribution, and stored per-phrase ranking history.
25b. Add explicit zero-data and one-check states so a single snapshot is never presented as a trend.
26. Restructure Site Health around a single `Fix this first` priority.
27. Add `What is wrong`, `Why it matters`, `What to do next`, and `Priority` to each issue group.
28. Collapse crawl terminology and raw URL evidence under `Technical details`.
29. Add a visible rescan or opportunity action where the backend supports it.
29a. Add visual issue-priority, affected-page, and scan-history views without introducing a synthetic health score.

### Sprint 7 — Intelligence activation and safety

**Completed 2026-07-29.** Reno and Lexington both passed production cycle, repeat-run idempotency, recommendation-only safety, and zero-execution verification. Each cycle generated two orchestrator recommendations from saved data, with provider checks, mutation scheduling, mutation execution, policy updates, and causal claims disabled.

30. Add a production activation mode that defaults to recommendation-only execution.
31. Tenant-scope every intelligence simulation, metric, outcome, and recommendation read.
32. Add database-backed intelligence-cycle jobs to the Vercel cron runner.
33. Generate idempotent recommendations, simulations, and metrics from stored campaign signals without triggering paid provider checks.
34. Keep mutation scheduling and execution disabled during recommendation-only cycles.
35. Surface evidence, confidence, freshness, and model/runtime truth on Opportunities.
36. Capture deduplicated recommendation-score checkpoints and expose plain-language outcome history.
36a. Run learning in observation-only mode with policy updates and causal claims disabled until enough real outcomes exist for review.
37. Verify Reno and Lexington cycles, cross-tenant isolation, repeat-run idempotency, and zero mutation delivery.

### Sprint 8 — Local Visibility map

38. Capture or resolve structured city, state/region, country, latitude, and longitude for every business location.
39. Resolve DataForSEO location identifiers automatically from structured location data.
40. Add a real interactive map centered on the selected location with a business pin and service-area context.
41. Add clear setup states for missing coordinates, provider connection, or map-rank coverage.
42. Add provider-backed geo-grid/map-rank visualization only after the base map and location normalization pass QA.
43. Keep decorative/base-map presence visually distinct from paid ranking intelligence.

### Sprint 9 — Cross-page cleanup and final visual polish

44. Standardize page introductions, scope labels, primary actions, loading, empty, and error states.
45. Remove duplicated setup panels from operational pages after setup is complete.
46. Consolidate location-sensitive controls into shared components.
47. Verify desktop, tablet, and mobile journeys for switching locations, reading rankings, finding the first technical fix, and opening the map.
48. Complete the broader visual redesign only after the new hierarchy passes task-based usability checks.

### Sprint 10 — Plain-language and visual product system

49. Expand the service-business language guide into a shared customer-copy
dictionary, banned-jargon list, readability checks, and AI-output validation.
50. Define one page hierarchy, an original accessible icon family, and shared
metric, trend, chart, filter, comparison, tooltip, details, and sparse-data
components.
51. Remove decorative cards, repeated badges, provider labels, and internal
status metadata unless they support a customer decision or action.
52. Standardize beneficial/harmful/neutral trend semantics with icons, words,
and accessible color treatment.

### Sprint 11 — Overview and Next Steps journey redesign

53. Rebuild Overview as an above-the-fold daily business briefing with key
results, useful date comparisons, meaningful charts, and one next action.
54. Rebuild Next Steps around Today, This week, and This month with persistent
checklists and one focused details view instead of repeating the same action
across multiple panels.
55. Replace recommendation-engine labels and evidence classifications with
direct service-owner language while keeping technical proof optional.
56. Pass five-second comprehension and task-based tests at desktop, tablet, and
mobile sizes.

### Sprint 12 — Cross-page visualization and usability rollout

57. Apply the approved hierarchy and component system to Search Rankings,
Local Search, Website Health, Directory Listings, Reviews, Competitors, Search
Value, Locations, Reports, Settings, and setup states.
58. Add decision-useful graphs, maps, comparisons, distributions, progress,
and history only where supported by real data; state clearly when a visual
would be incomplete or misleading.
59. Audit every page for duplicated data, repeated guidance, oversized empty
space, dead controls, unnecessary badges, and priority content below the fold.
60. Complete route-by-route visual regression, keyboard, screen-reader, and
five-second comprehension QA.

### Sprint 13 — Natural product voice and comprehension

61. Rewrite public and authenticated headlines around the outcome the owner
wants instead of announcing `plain English`, simplicity, AI, or the absence of
SEO tooling.
62. Write for a capable, busy service-business owner. Use natural spoken
language, concrete verbs, and specific business meaning without describing the
customer as non-technical or less tech-savvy.
63. Audit onboarding, page introductions, navigation, metrics, empty and error
states, actions, reports, notifications, and AI messages for self-conscious
product narration, filler, stacked abstractions, and familiar AI phrasing.
64. Add approved examples, counterexamples, prohibited phrases, and
read-aloud/five-second comprehension checks to the shared language guide and
automated copy contracts.
65. Use the public home-page direction `Know how your business is showing up on
Google` and `See which searches help customers find you, how each location is
doing, and what to work on next` as a reference, subject to data-truth review.
66. Require representative service-business owners to answer `What is this
page for?` and `What would you do next?` without coaching before the sprint is
accepted.

### Planned product UX — G1.3A customer usage credits

- Replace `Monthly data budget` and customer-visible dollar balances with
  `Insight Credits available this month`.
- Show the exact integer credit price before a paid action, then show used,
  reserved, remaining, and reset date in plain language.
- Keep vendor prices, dollar reservations, and margin reporting internal. Do
  not describe credits as cash, API tokens, or general AI tokens.
- Explain failed-work refunds and organization-owned credentials without
  exposing provider accounting details.

Completion record (2026-08-04):

- Settings now shows Insight Credits, the monthly balance, credits used and
  reserved, reset date, action prices, and automatic returns for failed work.
- Keyword Research shows the refresh ceiling before the paid check and the
  bounded AI sorting price beside that action.
- The tenant response and source tests prevent customer UI from exposing the
  internal monthly dollar budget or vendor-cost accounting.

### Planned product UX — VAL1 research-backed Search Value

- Put the paid-search replacement-value range, confidence, data coverage, and
  change from the selected comparison period at the top of Search Value.
- Let the owner open the total to see each phrase's position, measured or
  estimated clicks, researched CPC, contribution, location, source, and date.
- Visually separate Search Console-measured behavior from modeled scenarios,
  and explain changes caused by rankings, demand, CPC, data coverage, or a
  model update.
- Use `What similar visibility could cost in paid search`; never use revenue,
  profit, lead, or guaranteed-return language for this estimate.

### Follow-on product sprint — I1.4/T29 measured website and Google Profile actions

67. Separate the action workspace into `Improve your website` and `Improve your
Google Business Profile` so a service owner immediately understands where the
work will happen.
68. Put a compact real-metric strip beside every action: metric name, current
value, source date, target or supported range, and `check again` date.
69. After the waiting period, replace the forecast emphasis with a simple
before/after visual and `improved`, `about the same`, `worse`, or `not enough
information` result.
70. Keep source, scope, provider, device, and technical evidence available in
details while the default view answers `What do I do?`, `Which number should
move?`, and `Did it help?`.
71. Never display a success state from checklist completion alone. Require a
new same-scope provider measurement, and explain the missing connection or
baseline when a result cannot be measured.
72. Use live website measurements from CWV, Search Console, and governed crawl
facts. Use location-scoped Google Business Profile performance and reputation
metrics only after G1.4's authorized production connection is active.

Completion record (2026-08-03):
- The compact page-purpose pattern and shared owner decision panel now place
  the current result and next action above setup and supporting details.
- Real-data charts and maps remain on Rankings, Local Search, and Website
  Health; Listings, Search Value, Locations, Reports, and Connections add
  accessible progress or comparison visuals without inventing history.
- Duplicate summaries and setup-first layouts were reduced, and source tests
  enforce route coverage, one dismissible guide, and truthful visualization.

### Later product sprint — ENG1 verified progress and healthy habits

73. Create a small achievement system with three clearly different types:
foundation milestones, useful-work consistency badges, and verified-result
badges.
74. Put progress toward the next relevant achievement beside the related plan
without moving the current priority, metric, or next action below the fold.
75. When a badge is earned, show a brief accessible celebration that says what
the owner accomplished, which location it applies to, and which work or metric
proved it. Include a direct evidence link and one useful next goal.
76. Allow checklist completion to earn a plainly labeled habit badge, but
require a genuinely later same-scope provider measurement before granting any
improvement badge.
77. Favor weekly and monthly progress over brittle daily streaks. Add grace for
provider outages and missing observations, and never reward unnecessary scans,
repeated clicks, provider spend, or busywork.
78. Keep deterministic achievement rules and evidence authoritative. AI may
write the friendly celebration and next-goal explanation but cannot grant,
upgrade, or invent an achievement.
79. Add a compact achievement history and optional notification controls. Avoid
public leaderboards, shame, artificial urgency, pay-to-win rewards, intrusive
animation, and notification fatigue.
80. Use PA1 cohort measurement and explicit stop conditions to prove that the
system improves useful follow-through and retention before expanding the badge
catalog.

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
