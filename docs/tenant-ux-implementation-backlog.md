# Tenant UX Implementation Backlog

**Project:** SEO Accelerator Tool (InsightOS)
**Role:** Engineering execution reference
**Status:** Ready for implementation
**Date:** 2026-03-13
**Source docs:**
- `docs/ui-ux-productization-plan.md`
- `docs/tenant-ux-redesign-spec.md`

---

## 1. Executive Summary

This backlog converts the UX strategy and redesign spec into a precise, phase-ordered engineering task list. Every item includes: the exact files affected, whether the change is additive or a refactor, the dependency chain, regression risk level, and whether a backend call or feature flag is involved.

**Core constraint:** All Phase 1 work must be completable without touching any backend API contracts, without adding new dependencies, and without modifying the dashboard data-fetching logic. Each phase is designed to be independently deployable.

**Starting point facts from codebase inspection:**

| File | Key finding |
|---|---|
| `dashboard/page.tsx:30–40` | 9 nav items defined inline. 8 are `disabled: true`. |
| `types.ts:3–9` | `NavItem` has no `hidden` field. |
| `SidebarNav.tsx:42–79` | Renders `disabled` items with "Coming soon" badge. No `hidden` filter. |
| `AppShell.tsx:29` | Sidebar: `hidden ... xl:block`. No mobile nav exists. |
| `TopBar.tsx:25–27` | Search is a static `<div>`, not an `<input>`. |
| `TopBar.tsx:33–37` | "Alerts" and "Help" buttons have no `onClick`. |
| `InsightCard.tsx:34` | Action `<button>` has no `onClick` handler. |
| `EmptyState.tsx:23` | CTA `<button>` has no `onClick` handler. |
| `ActionDrawer.tsx:45–51` | Default "Approve"/"Schedule" fallback buttons have no `onClick`. |
| `types.ts:17–21` | `QuickAction` has `href?` and `onClickLabel?` but no `onClick` callback. |
| `platform/api.js` | `platformApi()` handles auth + token refresh. Returns `json.data`. |
| `dashboard/page.tsx` | Uses its own inline `fetch` with token refresh, separate from `platformApi`. |

---

## 2. Implementation Goals

1. Eliminate all dead-end navigation items from the customer-facing sidebar
2. Relabel all raw operator terms in the dashboard with plain-English copy
3. Wire all inert CTAs to functional behavior
4. Add a zero-state / first-run prompt for users with no campaign
5. Build a 3-step onboarding wizard using only existing backend APIs
6. Add three new tenant pages: Rankings, Reports Center, Opportunities
7. Add a minimal Settings page
8. Add mobile navigation drawer
9. Wire nav badge counts to real API data
10. Move raw operator forms off the main dashboard surface (after new pages are live)

---

## 3. Scope for Phase 1

**Theme:** No-risk UX triage. No new pages. No new API calls. No functional logic changes.

| # | Task | Type |
|---|---|---|
| 1.1 | Add `hidden?: boolean` to `NavItem` type | Type extension |
| 1.2 | Filter hidden nav items in `SidebarNav` | Additive filter |
| 1.3 | Mark 4 nav items hidden in dashboard nav config | Config change |
| 1.4 | Relabel dashboard form section headers and placeholders | Copy change |
| 1.5 | Add `onAction?: () => void` prop to `EmptyState` | Prop addition |
| 1.6 | Wire `EmptyState` CTA to scroll-to or open campaign form | Behavior wire |
| 1.7 | Add `onClick?: () => void` to `QuickAction` type | Type extension |
| 1.8 | Wire `InsightCard` action button to `onClick` if provided | Behavior wire |
| 1.9 | Add zero-state welcome prompt on dashboard when no campaign | Conditional render |
| 1.10 | Remove inert default buttons from `ActionDrawer` fallback | Cleanup |

---

## 4. Scope for Phase 2

**Theme:** First-run onboarding wizard. New component only. Uses existing API calls.

| # | Task | Type |
|---|---|---|
| 2.1 | Build `OnboardingWizard.tsx` (3-step component) | New component |
| 2.2 | Wire Step 1 to `POST /campaigns` | API call |
| 2.3 | Wire Step 3 to `POST /crawl/schedule` and `POST /rank/schedule` | API calls |
| 2.4 | Render wizard conditionally in `dashboard/page.tsx` when `campaigns.length === 0` | Conditional render |
| 2.5 | Redirect to dashboard on wizard completion | Navigation |

---

## 5. Scope for Phase 3

**Theme:** New pages (additive routes). All use existing backend APIs via `platformApi`.

| # | Task | Type |
|---|---|---|
| 3.1 | Build `app/(product)/reports/page.tsx` | New page |
| 3.2 | Build `app/(product)/opportunities/page.tsx` | New page |
| 3.3 | Build `app/(product)/rankings/page.tsx` | New page |
| 3.4 | Build `app/(product)/settings/page.tsx` (minimal) | New page |
| 3.5 | Enable nav items for Reports, Opportunities, Rankings, Settings | Config change |
| 3.6 | Wire Opportunities badge count to real `GET /recommendations` response | Data wire |

---

## 6. Scope for Phase 4

**Theme:** Mobile nav + dashboard form demotion. Depends on Phase 3 pages being live.

| # | Task | Type |
|---|---|---|
| 4.1 | Build `MobileNav.tsx` drawer component | New component |
| 4.2 | Add hamburger button to `TopBar.tsx` | Additive modification |
| 4.3 | Render `MobileNav` in `AppShell.tsx` | Additive modification |
| 4.4 | Move crawl form off main dashboard into a "Run scan" modal | Refactor (post-P3) |
| 4.5 | Move rank snapshot form to Rankings page | Refactor (post-P3) |
| 4.6 | Move report forms to Reports page | Refactor (post-P3) |

---

## 7. Features Explicitly Out of Scope

Do not build these. Do not create placeholder routes for these.

| Feature | Route | Reason | When to revisit |
|---|---|---|---|
| Site Health page | `/site-health` | Badge hardcoded, route missing, backend incomplete | P2 |
| Competitors page | `/competitors` | Needs comparison UX design not yet defined | P2 |
| Locations page | `/locations` | No tenant UX design, hierarchy complexity | P2 |
| Local Visibility page | `/local-visibility` | Needs map UX + dedicated workflow | P2 |
| TopBar search | — | Requires indexing strategy, not a quick build | P2 |
| Portfolio / Agency views | — | Separate product surface | P2+ |
| Fetch client consolidation | — | Engineering refactor, separate sprint | P2 |
| Backend test fixes | — | Engineering hygiene, separate sprint | P2 |

---

## 8. Route-Level Change Plan

### Existing routes — no structural change

| Route | File | Action |
|---|---|---|
| `/dashboard` | `(product)/dashboard/page.tsx` | Modify in-place (copy, conditional render, CTA wire) |
| `/login` | `login/page.jsx` | Do not touch |
| `/platform/**` | `platform/**` | Do not touch |
| `/legacy-dashboard` | `legacy-dashboard/page.jsx` | Do not touch |

### New routes to add (all additive, no impact on existing)

| Route | File to create | Phase |
|---|---|---|
| `/reports` | `(product)/reports/page.tsx` | Phase 3 |
| `/opportunities` | `(product)/opportunities/page.tsx` | Phase 3 |
| `/rankings` | `(product)/rankings/page.tsx` | Phase 3 |
| `/settings` | `(product)/settings/page.tsx` | Phase 3 |

### Routes to keep hidden (do NOT create files for these)

| Route | Status |
|---|---|
| `/locations` | Hidden from nav, no file created |
| `/local-visibility` | Hidden from nav, no file created |
| `/site-health` | Hidden from nav, no file created |
| `/competitors` | Hidden from nav, no file created |

**Note:** If any of these routes are accidentally navigated to (e.g., saved bookmark), Next.js will return a 404. This is acceptable — the routes were never live for tenant users.

---

## 9. Component-Level Change Plan

### `types.ts` — 2 changes

**Change A: Add `hidden` to `NavItem`**
- File: `frontend/app/(product)/components/types.ts`
- Current: `NavItem` type at line 3 has `href`, `label`, `badge?`, `active?`, `disabled?`
- Add: `hidden?: boolean`
- Type: Additive (backward compatible — existing nav items without `hidden` continue working)
- Risk: None

**Change B: Add `onClick` callback to `QuickAction`**
- File: `frontend/app/(product)/components/types.ts`
- Current: `QuickAction` at line 17 has `label`, `href?`, `onClickLabel?`
- Add: `onClick?: () => void`
- Type: Additive (backward compatible)
- Risk: None

---

### `SidebarNav.tsx` — 1 change

**Change: Filter hidden items before rendering**
- File: `frontend/app/(product)/components/SidebarNav.tsx`
- Current: Line 42 — `{items.map((item) => (` renders all items
- Change: Filter before map — `{items.filter(item => !item.hidden).map((item) => (`
- Type: Additive (one-word change, backward compatible)
- Risk: None — items without `hidden` field behave identically
- Backend dependency: None
- Feature flag: Not needed

---

### `InsightCard.tsx` — 1 change

**Change: Wire action button `onClick` from `QuickAction.onClick`**
- File: `frontend/app/(product)/components/InsightCard.tsx`
- Current: Line 34 — `<button className="...">` has no `onClick`
- Change: Add `onClick={insight.action.onClick}` to the button — only fires if the prop is provided
- Type: Additive (existing callers that don't provide `onClick` on their action object are unaffected)
- Risk: Low — the button was inert before, it either stays inert or gets a real handler
- Backend dependency: None
- Feature flag: Not needed

---

### `EmptyState.tsx` — 1 change

**Change: Add `onAction` prop and wire to button**
- File: `frontend/app/(product)/components/EmptyState.tsx`
- Current: Line 23 — `<button>` has no `onClick`. `EmptyStateProps` has no `onAction` field.
- Change: Add `onAction?: () => void` to `EmptyStateProps`. Wire to `<button onClick={onAction}>`.
- Type: Additive (existing callers without `onAction` get an inert button — same as before)
- Risk: None — no regression on existing call sites
- Backend dependency: None
- Feature flag: Not needed

---

### `ActionDrawer.tsx` — 1 change

**Change: Remove inert default fallback buttons**
- File: `frontend/app/(product)/components/ActionDrawer.tsx`
- Current: Lines 43–52 — if `actions` prop is not provided, renders inert "Approve" and "Schedule" buttons
- Change: Replace the fallback with `null` — if no `actions` prop, render nothing in that slot
- Type: Refactor of fallback only — does not affect callers that pass `actions` prop
- Risk: Low. Check all call sites of `<ActionDrawer>` in `dashboard/page.tsx` to confirm whether `actions` prop is passed. If it is, this change has zero visible effect. If it is not, the inert buttons disappear (desired behavior).
- Dependency: Inspect `dashboard/page.tsx` ActionDrawer usage before making this change
- Backend dependency: None

---

### `AppShell.tsx` — Phase 4 change

**Change: Add `MobileNav` rendering (Phase 4 only)**
- File: `frontend/app/(product)/components/AppShell.tsx`
- Current: Line 29 — sidebar `hidden ... xl:block`, no mobile nav
- Phase 4 change: Render `<MobileNav navItems={navItems} />` visible below `xl`, hidden above `xl`
- Type: Additive — does not modify desktop sidebar behavior
- Risk: Low — new component renders only on mobile viewport
- Backend dependency: None

---

### `TopBar.tsx` — Phase 4 change

**Change: Add hamburger button (Phase 4 only)**
- File: `frontend/app/(product)/components/TopBar.tsx`
- Current: No hamburger button, no mobile state
- Phase 4 change: Add `onMenuOpen?: () => void` prop. Render a hamburger `<button>` visible below `xl` only, calling `onMenuOpen`.
- Type: Additive — new prop, new button visible only on mobile
- Risk: Low — desktop layout unaffected
- Backend dependency: None

---

### New components to create

| Component | File | Phase | Purpose |
|---|---|---|---|
| `OnboardingWizard.tsx` | `(product)/components/OnboardingWizard.tsx` | Phase 2 | 3-step first-run flow |
| `MobileNav.tsx` | `(product)/components/MobileNav.tsx` | Phase 4 | Mobile drawer nav |

---

## 10. Navigation Change Plan

### Step 1: Add `hidden` to `NavItem` type (Phase 1, task 1.1)

**File:** `(product)/components/types.ts`
**Change:** Add `hidden?: boolean` to `NavItem` — one line addition.

### Step 2: Filter hidden items (Phase 1, task 1.2)

**File:** `(product)/components/SidebarNav.tsx`
**Change:** Wrap `.map()` call at line 42 with `.filter(item => !item.hidden)` — one word change.

### Step 3: Mark items hidden (Phase 1, task 1.3)

**File:** `(product)/dashboard/page.tsx`
**Current nav config at lines 30–40:**

```
{ href: "/locations",       label: "Locations",       disabled: true }
{ href: "/rankings",        label: "Rankings",         disabled: true }
{ href: "/local-visibility",label: "Local Visibility", disabled: true }
{ href: "/site-health",     label: "Site Health",      badge: "3", disabled: true }
{ href: "/competitors",     label: "Competitors",      disabled: true }
{ href: "/opportunities",   label: "Opportunities",    badge: "5", disabled: true }
{ href: "/reports",         label: "Reports",          disabled: true }
{ href: "/settings",        label: "Settings",         disabled: true }
```

**Target state after Phase 1:**

| Item | Action | Rationale |
|---|---|---|
| Locations | Add `hidden: true` | No tenant page, no timeline |
| Rankings | Keep, leave `disabled: true` | Will be built in Phase 3 |
| Local Visibility | Add `hidden: true` | Needs dedicated workflow, no timeline |
| Site Health | Add `hidden: true` | Badge hardcoded, route missing |
| Competitors | Add `hidden: true` | No UI designed |
| Opportunities | Keep, leave `disabled: true` | Will be built in Phase 3 |
| Reports | Keep, leave `disabled: true` | Will be built in Phase 3 |
| Settings | Keep, leave `disabled: true` | Will be built in Phase 3 |

**Target state after Phase 3:**

Flip `disabled: true` → `disabled: false` (or remove `disabled`) for Rankings, Reports, Opportunities, Settings once their pages are live.

### Important: Verify before hiding

Before adding `hidden: true` to any item, search for direct `<Link href="...">` or `router.push()` references to those paths in the codebase. If none exist, it is safe to hide.

```
Paths to check: /locations, /local-visibility, /site-health, /competitors
```

---

## 11. Dashboard Change Plan

### Phase 1 changes (copy only, no functional changes)

**Task 1.4 — Relabel operator form sections**

All changes are string replacements in `dashboard/page.tsx`. No logic changes.

| Location | Current text | Replace with |
|---|---|---|
| Line ~994 eyebrow | `"Workflow controls"` | `"Actions"` |
| Line ~995 title | `"Operate the live campaign"` | `"Run checks and reports"` |
| Line ~996 summary | `"These controls are the working product flow..."` | Remove or simplify to one sentence |
| Line ~1003 label | `"Campaign"` | `"Your business"` |
| Line ~1010 placeholder | `"Campaign name"` | `"Business name"` |
| Line ~1016 placeholder | `"example.com"` | `"Your website (example.com)"` |
| Line ~1024 button | `"Create Campaign"` | `"Add your business"` |
| Line ~1055 label | `"Crawl"` | `"Website scan"` |
| Line ~1062 placeholder | `"https://example.com"` | Auto-populate from campaign domain |
| Line ~1078 button | `"Run Crawl"` | `"Run website scan"` |
| Line ~1084 label | `"Rank"` | `"Search position check"` |
| Line ~1091 placeholder | `"Core Terms"` | Remove field or hide (default silently) |
| Line ~1097 placeholder | `"local seo agency"` | `"What customers search for (e.g. plumber near me)"` |
| Line ~1103 placeholder | `"US"` | Remove field or hide (default silently) |
| Line ~1111 button | `"Run Rank Snapshot"` | `"Check search positions"` |
| Line ~1117 label | `"Reports"` | `"Reports"` (keep) |
| Line ~1127 input type=number | Month number raw input | Phase 3: move to Reports page |
| Line ~1133 placeholder | `"admin@local.dev"` | `"Email address to send report"` |
| Line ~1142 button | `"Generate Report"` | `"Create report"` |
| Line ~1149 button | `"Deliver Latest"` | `"Send to email"` |

**Note on "Crawl Type" selector (lines 1065–1072):** Hide the `<select>` for `crawlType` from the user entirely. The `crawlType` state and the API call don't change — only the UI selector is hidden. Default to `"deep"`. This is a one-line change: wrap the `<select>` in `{false && ...}` or remove it.

**Note on "Cluster Name" and "Location Code" fields:** Same approach — hide from UI, keep state defaults. `clusterName` defaults to `"Core Terms"`, `locationCode` defaults to `"US"`. These are already initialized in component state. Hiding the inputs does not break the API call.

### Phase 1 — Zero-state welcome prompt (task 1.9)

**File:** `dashboard/page.tsx`

After campaigns are loaded and `campaigns.length === 0`, render a welcome section instead of the empty KPI grid and the operator forms. This is a conditional render — not a replacement of the data fetching.

```tsx
// Guard condition to add after campaigns are resolved
if (!isLoading && campaigns.length === 0) {
  return (
    <AppShell ...>
      <EmptyState
        title="Welcome to InsightOS"
        summary="Let's get your business set up so we can start tracking your online visibility."
        actionLabel="Set up your business"
        onAction={() => /* scroll to campaign form or open wizard */}
      />
    </AppShell>
  );
}
```

The existing loading state and the main dashboard render path are not touched.

### Phase 4 — Form demotion (after Phase 3 pages are live)

Once Reports, Rankings, and Opportunities pages exist:
- Move report generate/deliver forms to `/reports` page
- Move rank snapshot form to `/rankings` page
- Move crawl form to a "Run scan" button with a confirmation dialog on dashboard
- Remove "Workflow controls" section from main dashboard JSX

This is Phase 4 work. Do not start this until Phase 3 pages are tested and live.

---

## 12. Onboarding Flow Change Plan

### Files

| File | Action | Phase |
|---|---|---|
| `(product)/components/OnboardingWizard.tsx` | Create (new) | Phase 2 |
| `(product)/dashboard/page.tsx` | Add conditional render | Phase 2 |

### Component design

`OnboardingWizard` is a self-contained component. It manages its own step state (`step: 1 | 2 | 3`). It receives one prop: `onComplete: () => void`.

**Step 1 — Business basics**
- Inputs: business name (→ `campaignName`), website URL (→ `campaignDomain`)
- Button: "Continue" → calls `POST /campaigns` → on success, advance to step 2
- Error: show inline if API call fails. "We couldn't save your info. Please try again."
- No operator language visible

**Step 2 — Focus area**
- Inputs: work type (dropdown → maps to `clusterName`), city/area served (text → maps to `locationCode`)
- Button: "Continue" → store values in component state, advance to step 3
- No API call on this step — values used in step 3

**Step 3 — Running first check**
- On mount: fire `POST /crawl/schedule` (with campaign ID from step 1) and `POST /rank/schedule` (with values from step 2)
- Show progress indicator while calls are in-flight
- "We're scanning your website and checking where you show up online"
- "This usually takes about 2 minutes"
- On both calls resolved: show success state with "See your first results →" button
- Button calls `onComplete()` which triggers campaign refetch in dashboard

### API calls in wizard

| Step | API | Method | Payload fields |
|---|---|---|---|
| Step 1 | `/campaigns` | POST | `name`, `domain` |
| Step 3a | `/crawl/schedule` | POST | `campaign_id`, `seed_url`, `crawl_type: "deep"` |
| Step 3b | `/rank/schedule` | POST | `campaign_id`, `keyword`, `cluster_name`, `location_code` |

Use `platformApi` from `platform/api.js` for all three calls. Do not replicate the inline fetch pattern.

### Conditional render in dashboard

```tsx
// At top of dashboard render, after campaigns load
if (!isLoading && campaigns.length === 0 && !showWizard) {
  return <AppShell ...><EmptyState ... onAction={() => setShowWizard(true)} /></AppShell>;
}
if (showWizard) {
  return <AppShell ...><OnboardingWizard onComplete={() => { setShowWizard(false); refetchCampaigns(); }} /></AppShell>;
}
// Existing dashboard render continues below
```

**Risk:** This conditional is placed before the existing JSX return. The existing dashboard render path is completely untouched.

### Onboarding API consideration

`onboarding.py` exists in backend. Before using individual campaign/crawl/rank calls, inspect the `POST /onboarding` contract. If it accepts a single payload and returns a campaign ID, prefer it over three separate calls — it reduces race conditions. If it has unclear error handling or untested behavior, use the individual calls as specified above.

---

## 13. Rankings Page Build Plan

### File to create

`frontend/app/(product)/rankings/page.tsx`

### Type: Additive — new file in existing route group. No existing files modified.

### APIs

| Call | Method | Endpoint | When |
|---|---|---|---|
| Fetch rank trends | GET | `/rank/trends?campaign_id={id}` | On page load / campaign change |
| Fetch rank snapshots | GET | `/rank/snapshots?campaign_id={id}` | On page load |
| Add keyword + schedule | POST | `/rank/keywords` then `POST /rank/schedule` | "Add search term" action |

Use `platformApi` for all calls.

### Page state

- `selectedCampaignId: string` — read from URL param or localStorage
- `trends: RankTrend[]` — from `/rank/trends`
- `snapshots: RankSnapshot[]` — from `/rank/snapshots`
- `isLoading: boolean`
- `error: string | null`
- `showAddModal: boolean`

### Layout implementation

Reuse these existing components:

| Component | Purpose |
|---|---|
| `AppShell` | Page wrapper with nav and topbar |
| `KpiCard` | Summary KPIs (keywords tracked, moved up, moved down) |
| `ChartCard` | Ranking trend chart wrapper |
| `EmptyState` | When no keywords tracked |
| `ComparisonTable` | Keyword table (position, change, last checked) |
| `TrustStatusBar` | Data freshness |

Do not build a custom table component. Use `ComparisonTable.tsx` with keyword data shaped to its props.

### "Add search term" modal

Plain-English prompt: "What do customers search for to find you?" Single input, submit button. On submit: calls `POST /rank/keywords`, then `POST /rank/schedule`. Refresh trends on completion.

### Empty state

Use `<EmptyState>` with:
- title: `"No search terms tracked yet"`
- summary: `"Add the phrases your customers use to find businesses like yours."`
- actionLabel: `"Add your first search term"`
- onAction: `() => setShowAddModal(true)`

### Backend dependency: None (APIs already exist)
### Feature flag: `NEXT_PUBLIC_SHOW_RANKINGS=true` recommended for staged rollout
### Regression risk: None — new file, no existing code modified

---

## 14. Reports Center Build Plan

### File to create

`frontend/app/(product)/reports/page.tsx`

### Type: Additive — new file in existing route group. No existing files modified.

### APIs

| Call | Method | Endpoint | When |
|---|---|---|---|
| List reports | GET | `/reports?campaign_id={id}` | On page load |
| Get report detail | GET | `/reports/{id}` | On "View" click |
| Generate report | POST | `/reports/generate` | On "Create this month's report" confirm |
| Deliver report | POST | `/reports/{id}/deliver` | On "Send to email" confirm |
| Get schedule | GET | `/reports/schedule` | On page load |
| Update schedule | PUT | `/reports/schedule` | On schedule edit save |

Use `platformApi` for all calls.

### Page state

- `reports: Report[]`
- `selectedReport: Report | null`
- `schedule: ReportSchedule | null`
- `isLoading: boolean`
- `isGenerating: boolean`
- `showGenerateModal: boolean`
- `showDeliverModal: boolean`
- `error: string | null`

### Layout implementation

Reuse these existing components:

| Component | Purpose |
|---|---|
| `AppShell` | Page wrapper |
| `ReportPreview` | Report detail view when a report is selected |
| `EmptyState` | When no reports exist |
| `TrustStatusBar` | Data freshness |

### "Create this month's report" flow

1. User clicks "Create this month's report" button
2. Modal appears: "Create your [Month Year] report" — no month number input. Derive month from `new Date()`.
3. Confirm button → `POST /reports/generate` with `{ campaign_id, month_number: currentMonth }`
4. Loading state: "Building your report..."
5. On success: "Report ready! [View report] [Send to email]"

### Report delivery flow

1. User clicks "Send to email" on a report row
2. Modal: pre-filled email from account data (`GET /auth/me`), confirm button
3. `POST /reports/{id}/deliver` with `{ email }`
4. Success: "Report sent to [email]"

### Dashboard cleanup (Phase 4)

After this page is live and tested, remove "Generate Report" and "Deliver Latest" buttons from `dashboard/page.tsx` and replace with a link: "View reports →" navigating to `/reports`.

### Backend dependency: None (APIs already exist)
### Feature flag: `NEXT_PUBLIC_SHOW_REPORTS=true` recommended for staged rollout
### Regression risk: None — new file

---

## 15. Opportunities / Action Center Build Plan

### File to create

`frontend/app/(product)/opportunities/page.tsx`

### Type: Additive — new file. No existing files modified.

### APIs

| Call | Method | Endpoint | When |
|---|---|---|---|
| List recommendations | GET | `/recommendations?campaign_id={id}` | On page load |
| Dismiss recommendation | PATCH or DELETE | Check API contract | On "Dismiss" click |

**Before implementing dismiss:** Inspect `recommendations.py` to confirm what endpoint accepts a "dismiss" or "acknowledge" action. If no such endpoint exists, implement client-side dismiss (remove from local state only, no API call). Do not block page build on this.

Use `platformApi` for all calls.

### Page state

- `recommendations: Recommendation[]`
- `dismissed: string[]` — local session state for client-side dismiss
- `isLoading: boolean`
- `error: string | null`

### Layout implementation

Reuse `InsightCard.tsx` for each recommendation card. The `InsightCard` action button will be wired (after Phase 1 change B) to call the dismiss handler or navigate to a details view.

Severity grouping: render High impact items first, then Medium, then Low. Sort by a `priority` or `impact` field from the API response. If the field name differs, inspect the API response shape first.

### Badge count wiring

After this page is built, update the Opportunities nav item badge from hardcoded `"5"` to the real count:

```tsx
// In dashboard/page.tsx navItems, after fetching recommendations
{ href: "/opportunities", label: "Opportunities", badge: String(recommendations.length) }
```

This requires a lightweight `GET /recommendations` call in the dashboard page's `useEffect`. Keep it separate from the opportunities page load. Use `platformApi`.

### Empty state

Use `<EmptyState>` with:
- title: `"No open opportunities"`
- summary: `"We'll alert you when we find ways to improve your visibility."`
- No CTA needed on empty state

### Backend dependency: None for read. Verify dismiss endpoint before implementing that action.
### Feature flag: `NEXT_PUBLIC_SHOW_OPPORTUNITIES=true` recommended
### Regression risk: None — new file

---

## 16. Settings Page Build Plan

### File to create

`frontend/app/(product)/settings/page.tsx`

### Type: Additive — new file. No existing files modified.

### APIs

| Call | Method | Endpoint | When |
|---|---|---|---|
| Get account info | GET | `/auth/me` | On page load |
| Get report schedule | GET | `/reports/schedule` | On page load |

P1 scope: read-only display only. No edit functionality needed for initial launch. Keep edit CTAs visible but they can open a "Coming soon" tooltip for now. Do not ship inert buttons without a tooltip — add a `title="Coming soon"` attribute minimum.

### Page state

- `me: Me | null` — from `/auth/me`
- `schedule: ReportSchedule | null` — from `/reports/schedule`
- `isLoading: boolean`

### Layout

Three sections:

1. **Account** — Email (read-only). Password change CTA (tooltip: "Coming soon" for P1).
2. **Notifications** — Report delivery frequency and email from schedule data.
3. **Business** — Business name and website from campaign data (or `me` response if it includes this).

Use `platformApi` for all calls.

### Backend dependency: None — uses existing `/auth/me` and `/reports/schedule`
### Feature flag: `NEXT_PUBLIC_SHOW_SETTINGS=true` recommended
### Regression risk: None — new file

---

## 17. Mobile Navigation Build Plan

### Files

| File | Action | Phase |
|---|---|---|
| `(product)/components/MobileNav.tsx` | Create (new) | Phase 4 |
| `(product)/components/TopBar.tsx` | Add `onMenuOpen` prop + hamburger button | Phase 4 |
| `(product)/components/AppShell.tsx` | Add `<MobileNav>` render + open/close state | Phase 4 |

### `MobileNav.tsx` component design

Props:
- `navItems: NavItem[]` — same array passed to `SidebarNav`
- `isOpen: boolean`
- `onClose: () => void`

Renders:
- A fixed-position overlay (dim background) when `isOpen`
- A slide-in drawer from the left containing `<SidebarNav items={navItems} />`
- Tap on overlay closes the drawer (calls `onClose`)
- Visible only below `xl` breakpoint (`xl:hidden` on the wrapper)

Does not render on desktop. Does not affect `SidebarNav` or the existing sidebar div in `AppShell`.

### `TopBar.tsx` — new prop

Add `onMenuOpen?: () => void` prop. Render a `<button>` at the left edge of the header, visible only below `xl` (`xl:hidden`), that calls `onMenuOpen`. Symbol: three horizontal lines (hamburger). No icon library needed — use plain CSS or a Unicode character.

### `AppShell.tsx` — state and render

Add internal `const [mobileNavOpen, setMobileNavOpen] = useState(false)`. Pass `onMenuOpen={() => setMobileNavOpen(true)}` to `TopBar`. Render `<MobileNav navItems={navItems} isOpen={mobileNavOpen} onClose={() => setMobileNavOpen(false)} />` as a sibling to the existing layout divs.

**The existing sidebar `div` at line 29 is not changed.** The mobile nav is purely additive.

### Close on route change

In `MobileNav.tsx`, use `usePathname()` from `next/navigation` in a `useEffect` to call `onClose()` whenever the path changes.

### Type: Additive — no existing layout or data logic modified
### Backend dependency: None
### Regression risk: Low — desktop layout unchanged. Verify at `xl` breakpoint that sidebar still appears correctly.

---

## 18. CTA Repair Plan

All four inert CTA locations require code changes. All changes are additive (adding props or handlers). None require new API calls for Phase 1.

### CTA 1: `EmptyState` button (Phase 1, task 1.5–1.6)

**Current:** `EmptyState.tsx:23` — `<button>` with no `onClick`
**Fix:**
1. Add `onAction?: () => void` to `EmptyStateProps`
2. Add `onClick={onAction}` to the button element
3. In `dashboard/page.tsx`, update `<EmptyState>` calls to pass `onAction`

**Dashboard zero-state `onAction`:** scroll to the campaign form section using `document.getElementById('campaign-form')?.scrollIntoView()`. Or, in Phase 2, trigger `setShowWizard(true)`.

**Call site search:** Find all uses of `<EmptyState` in the codebase. Each must pass a meaningful `onAction` or the button should be conditionally hidden when no action is available.

---

### CTA 2: `InsightCard` action button (Phase 1, task 1.7–1.8)

**Current:** `InsightCard.tsx:34` — `<button>` with no `onClick`. `QuickAction` type has no `onClick` field.
**Fix:**
1. Add `onClick?: () => void` to `QuickAction` in `types.ts`
2. Add `onClick={insight.action.onClick}` to the `<button>` in `InsightCard.tsx:34`
3. In `dashboard/page.tsx`, update each `InsightCard` usage to pass a real `action.onClick`

**Dashboard InsightCard call sites (approx. lines 960–988):**

| Card | Current action label | Phase 1 behavior |
|---|---|---|
| Campaign insight | `"Manage campaign"` | `onClick: () => document.getElementById('campaign-form')?.scrollIntoView()` |
| Rankings insight | `"Run rankings"` | `onClick: () => document.getElementById('rank-form')?.scrollIntoView()` |
| Reports insight | `"Manage reports"` | `onClick: () => document.getElementById('report-form')?.scrollIntoView()` |

Phase 3 update: change these `onClick` handlers to `router.push('/rankings')`, `router.push('/reports')` etc. once those pages exist.

---

### CTA 3: `ActionDrawer` default buttons (Phase 1, task 1.10)

**Current:** `ActionDrawer.tsx:43–52` — fallback renders "Approve" and "Schedule" buttons with no `onClick`
**Fix:** Replace the fallback `<>...</>` with `null`

```tsx
// Before
{actions ?? (<><button>Approve</button><button>Schedule</button></>)}

// After
{actions ?? null}
```

**Call site check:** Inspect `dashboard/page.tsx` for `<ActionDrawer` usage. Confirm whether `actions` prop is passed. If it is, this change has zero user-visible effect. If it is not, the inert buttons disappear — which is the desired result.

---

### CTA 4: `TopBar` Alerts and Help buttons (defer to Phase 2+)

**Current:** `TopBar.tsx:33–37` — "Alerts" and "Help" buttons with no `onClick`
**Phase 1 recommendation:** Add `title="Coming soon"` attribute to both buttons. This is minimal — not fully functional, but not silently inert.
**Phase 2:** Wire "Help" to an external link or a help modal. Wire "Alerts" to a notification system when one exists.
**Risk of leaving as-is:** Low for launch. These are secondary actions. Prioritize the primary CTAs first.

---

## 19. API Reuse Map

All new pages use `platformApi` from `frontend/app/platform/api.js`. Do not replicate the inline fetch pattern from `dashboard/page.tsx`.

| Page | API calls | Endpoint |
|---|---|---|
| Rankings | Fetch trends | `GET /rank/trends?campaign_id=` |
| Rankings | Fetch snapshots | `GET /rank/snapshots?campaign_id=` |
| Rankings | Add keyword | `POST /rank/keywords` |
| Rankings | Schedule check | `POST /rank/schedule` |
| Reports | List reports | `GET /reports?campaign_id=` |
| Reports | Generate | `POST /reports/generate` |
| Reports | Get detail | `GET /reports/{id}` |
| Reports | Deliver | `POST /reports/{id}/deliver` |
| Reports | Get schedule | `GET /reports/schedule` |
| Reports | Update schedule | `PUT /reports/schedule` |
| Opportunities | List recs | `GET /recommendations?campaign_id=` |
| Settings | Account info | `GET /auth/me` |
| Settings | Report schedule | `GET /reports/schedule` |
| Onboarding | Create campaign | `POST /campaigns` |
| Onboarding | Schedule crawl | `POST /crawl/schedule` |
| Onboarding | Schedule rank | `POST /rank/schedule` |
| Dashboard (badge) | Count recs | `GET /recommendations?campaign_id=` |

**`platformApi` usage pattern for new pages:**

```ts
// Standard fetch pattern for new pages
const data = await platformApi('/rank/trends?campaign_id=' + campaignId);
```

Errors thrown by `platformApi` are already in user-readable form (extracted from `error.message` or `errors[0].message`). Catch and display them with a retry CTA.

**Do not consolidate the dashboard's inline fetch with `platformApi` in these sprints.** That is a separate P2 engineering task with meaningful regression risk.

---

## 20. Feature Flag Plan

Feature flags allow new pages to be tested internally before enabling them for all users. All flags are environment variables read at build/runtime in Next.js.

| Flag | Controls | Default | When to enable |
|---|---|---|---|
| `NEXT_PUBLIC_SHOW_RANKINGS` | Rankings nav item visibility and page | `false` | After page is built and tested internally |
| `NEXT_PUBLIC_SHOW_REPORTS` | Reports nav item visibility and page | `false` | After page is built and tested internally |
| `NEXT_PUBLIC_SHOW_OPPORTUNITIES` | Opportunities nav item visibility and page | `false` | After page is built and tested internally |
| `NEXT_PUBLIC_SHOW_SETTINGS` | Settings nav item visibility and page | `false` | After page is built and tested internally |
| `NEXT_PUBLIC_SHOW_ONBOARDING` | Onboarding wizard for zero-campaign state | `false` | After wizard is built and tested |

**Usage pattern:**

```ts
// In nav config or page guard
if (process.env.NEXT_PUBLIC_SHOW_RANKINGS !== 'true') {
  // hide nav item or redirect away
}
```

**Phase 1 changes do not need feature flags** — they are copy changes and CTA wires with no functional risk.

**Alternative approach:** If environment variable management is overhead, use the `hidden: true` nav field as a manual flag instead. Set `hidden: false` on a nav item only when the page is ready to ship. This requires a code deploy but avoids environment configuration.

---

## 21. Regression Risk Table

| Task | Risk Level | What could break | Prevention |
|---|---|---|---|
| 1.1 — Add `hidden` to NavItem type | None | Nothing | Type addition only |
| 1.2 — Filter hidden items in SidebarNav | None | Nav rendering if filter breaks items without `hidden` | Use `!item.hidden` (not `item.hidden === false`) — falsy check handles undefined |
| 1.3 — Mark 4 items hidden | None | Nav links if anything links to hidden routes | Search codebase for `href="/locations"` etc. before hiding |
| 1.4 — Relabel dashboard copy | None | Nothing functional | String changes only |
| 1.5–1.6 — Wire EmptyState CTA | None | EmptyState display if `onAction` is undefined | Button with `undefined` onClick is inert — same as before |
| 1.7–1.8 — Wire InsightCard button | None | InsightCard display if `onClick` is undefined | `onClick={undefined}` on a button is inert — same as before |
| 1.9 — Zero-state detection | Low | Dashboard if campaign fetch state is wrong | Guard with `!isLoading && campaigns.length === 0` — not just `campaigns.length === 0` |
| 1.10 — Remove ActionDrawer fallback buttons | Low | ActionDrawer if `actions` prop is not passed by callers | Check all `<ActionDrawer>` call sites before making this change |
| 2.1–2.5 — Onboarding wizard | Low | Dashboard render if conditional breaks | Wizard rendered only when `campaigns.length === 0`. Existing path untouched. |
| 3.1–3.4 — New pages | None | Nothing — new files only | N/A |
| 3.5 — Enable nav items | Low | Nav routing if page doesn't exist | Only enable after page file is confirmed live |
| 3.6 — Wire badge count | Medium | Dashboard perf if recommendations fetch is slow | Add to existing `useEffect`, handle loading/error silently (don't block dashboard render) |
| 4.1–4.3 — Mobile nav | Low | AppShell layout if MobileNav import breaks | Import guard, test at xl boundary |
| 4.4–4.6 — Form demotion | Medium | Dashboard operator workflow if forms removed before replacement is live | Only do this after Phase 3 pages are confirmed working |

**Never-touch list (zero tolerance for accidental modification):**

- `app/platform/**` — control plane
- `app/login/page.jsx` — auth flow
- `app/legacy-dashboard/page.jsx` — legacy route
- `backend/app/api/v1/**` — no backend changes in any phase
- `app/layout.jsx` — root layout

---

## 22. QA / Validation Checklist

Run this checklist after each phase before merging.

### Phase 1 QA

- [ ] Sidebar shows exactly 5 items: Dashboard (active), Rankings (disabled), Reports (disabled), Opportunities (disabled), Settings (disabled)
- [ ] Sidebar does NOT show: Locations, Local Visibility, Site Health, Competitors
- [ ] Clicking disabled nav items shows "Coming soon" badge but does not navigate
- [ ] Dashboard form labels display in plain English (no "Crawl", "Rank", "Cluster Name", "Location Code", "Seed URL" visible)
- [ ] Crawl type selector is hidden; crawl still works with default type
- [ ] Cluster name and location code inputs are hidden; rank still works with defaults
- [ ] InsightCard action buttons do not throw errors when clicked
- [ ] EmptyState CTA button does not throw errors when clicked
- [ ] When logged in with no campaigns: welcome prompt is shown instead of empty KPI grid
- [ ] When logged in with campaigns: normal dashboard renders correctly (no regression)
- [ ] Platform routes (`/platform`, `/platform/orgs`, etc.) are unaffected
- [ ] Login flow is unaffected
- [ ] Desktop layout (sidebar visible at xl) is unchanged

### Phase 2 QA

- [ ] New user with no campaign sees welcome prompt → "Set up your business" opens wizard
- [ ] Wizard Step 1: business name and website inputs work, "Continue" creates a campaign via API
- [ ] Wizard Step 2: work type and city inputs work, "Continue" advances to step 3
- [ ] Wizard Step 3: crawl and rank APIs are called, progress indicator shows, success message appears
- [ ] "See your first results" navigates back to dashboard with campaign now loaded
- [ ] If wizard API call fails, error message is shown with retry option
- [ ] User with existing campaign never sees the wizard
- [ ] Campaign created via wizard appears in campaign dropdown on dashboard

### Phase 3 QA

- [ ] `/rankings` page loads with rank trends and snapshots for selected campaign
- [ ] Rankings empty state renders when no keywords are tracked
- [ ] "Add search term" modal submits and refreshes table
- [ ] `/reports` page loads report list for selected campaign
- [ ] "Create this month's report" generates a report with current month derived automatically
- [ ] "Send to email" delivers report and shows confirmation
- [ ] Report preview renders using `ReportPreview` component
- [ ] `/opportunities` page loads recommendations list
- [ ] Each opportunity card shows issue, impact, and action
- [ ] "Dismiss" removes card from view
- [ ] Opportunities badge in sidebar reflects real count (not hardcoded "5")
- [ ] `/settings` page loads account info from `/auth/me`
- [ ] Nav items for Rankings, Reports, Opportunities, Settings are no longer `disabled`
- [ ] All new pages use `platformApi` — no inline fetch duplication
- [ ] Token expiry on new pages triggers refresh and retries correctly (test with expired token)

### Phase 4 QA

- [ ] On viewport below `xl`: hamburger button appears in TopBar
- [ ] Tapping hamburger opens nav drawer from left
- [ ] Drawer contains same nav items as desktop sidebar
- [ ] Tapping outside drawer closes it
- [ ] Navigating from drawer closes it
- [ ] Desktop layout at `xl` and above: no hamburger visible, sidebar renders as before
- [ ] Dashboard no longer shows raw operator forms after demotion
- [ ] Reports page has generate/deliver functionality (not dashboard)
- [ ] Rankings page has rank snapshot functionality (not dashboard)

---

## 23. Recommended Order of Engineering Execution

This is the safest linear order within each phase. Each numbered item can be deployed independently.

### Phase 1 — Complete in a single PR if possible

1. `types.ts` — add `hidden?: boolean` to `NavItem`, add `onClick?: () => void` to `QuickAction`
2. `SidebarNav.tsx` — add `.filter(item => !item.hidden)` before `.map()`
3. `dashboard/page.tsx` — add `hidden: true` to Locations, Local Visibility, Site Health, Competitors nav items
4. `EmptyState.tsx` — add `onAction?: () => void` prop, wire to button `onClick`
5. `InsightCard.tsx` — wire `insight.action.onClick` to button `onClick`
6. `ActionDrawer.tsx` — replace inert fallback buttons with `null`
7. `dashboard/page.tsx` — relabel all form section headers and field placeholders (copy changes)
8. `dashboard/page.tsx` — hide crawl type `<select>`, cluster name `<input>`, location code `<input>` from UI (keep state/API logic)
9. `dashboard/page.tsx` — wire `InsightCard` action `onClick` handlers to scroll-to targets
10. `dashboard/page.tsx` — add zero-state conditional render (welcome prompt when `campaigns.length === 0`)

**Phase 1 validation:** Run the Phase 1 QA checklist before any Phase 2 work begins.

### Phase 2 — Single PR or two small PRs

11. `OnboardingWizard.tsx` — build wizard component (3 steps, self-contained)
12. `dashboard/page.tsx` — add wizard conditional render

**Phase 2 validation:** Run the Phase 2 QA checklist before any Phase 3 work begins.

### Phase 3 — One PR per page (4 PRs)

13. `reports/page.tsx` — build Reports Center. Enable Reports nav item. QA reports checklist.
14. `opportunities/page.tsx` — build Opportunities page. Enable Opportunities nav item. QA opportunities checklist.
15. `rankings/page.tsx` — build Rankings page. Enable Rankings nav item. QA rankings checklist.
16. `settings/page.tsx` — build Settings page. Enable Settings nav item. QA settings checklist.
17. `dashboard/page.tsx` — wire Opportunities badge count to real recommendations fetch.

**Phase 3 validation:** Run the Phase 3 QA checklist. Confirm all 5 nav items work end to end.

### Phase 4 — Two PRs

18. `MobileNav.tsx` + `TopBar.tsx` + `AppShell.tsx` — mobile nav drawer. QA mobile checklist.
19. `dashboard/page.tsx` — form demotion (remove operator forms, replace with nav links to Phase 3 pages).

**Phase 4 validation:** Run the Phase 4 QA checklist. Full regression test across all pages.

---

## Best First Implementation Slice

**Implement Phase 1, items 1–3 only (types, filter, hide).**

This is the single highest-impact, lowest-risk change in the entire backlog:

1. Add `hidden?: boolean` to `NavItem` type — 1 line
2. Filter hidden items in `SidebarNav.tsx` — 1 word (`.filter(item => !item.hidden).`)
3. Add `hidden: true` to Locations, Local Visibility, Site Health, Competitors — 4 lines

**Total lines of code changed: ~7. Zero logic changes. Zero API changes. Zero component structure changes.**

**Impact:** The sidebar immediately goes from 9 items (8 dead ends) to 5 items (1 active, 4 clearly disabled but with a roadmap). The product stops promising features that don't exist. User trust improves on first load without touching any working functionality.

**This can be code-reviewed, tested, and deployed in under one hour.** It establishes the pattern (the `hidden` field) that all subsequent nav changes will use. It is the safest possible entry point into the full redesign.

After this ships and is confirmed stable, proceed with items 4–10 to complete Phase 1.
