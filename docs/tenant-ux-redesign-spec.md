# Tenant UX Redesign Spec

**Project:** SEO Accelerator Tool (InsightOS)
**Role:** Product / UX Spec
**Status:** Pre-implementation spec — no code generated yet
**Date:** 2026-03-13
**Companion doc:** `docs/ui-ux-productization-plan.md`

---

## 1. Product UX Goal

Make a non-technical home-service business owner feel in control of their local online presence — without needing to understand SEO, crawlers, keyword clusters, or API concepts.

The product should behave like a knowledgeable assistant that:
- Tells the user what happened
- Explains why it matters in business terms
- Recommends the one best action to take next

Every screen should move the user forward. No dead ends. No jargon. No silent failures.

---

## 2. Primary User Type

**Home-service business owner (SMB)**

- Runs a plumbing, HVAC, landscaping, cleaning, or similar local service business
- Has a website but did not build it themselves
- Checks business tools on mobile and occasionally on desktop
- Cares about: "Are customers finding me online?" and "Is my business growing?"
- Does not know what a "keyword cluster," "crawl type," "location code," or "rank snapshot" is
- Will stop using a product that confuses them within the first 2-3 sessions
- Trusts data when it is shown in the context of their business (revenue potential, customer reach)

**Mental model:** "Google is where customers find me. I want to show up higher. Tell me what to fix."

---

## 3. Secondary User Type

**Agency account manager / local SEO practitioner**

- Manages multiple client accounts (subaccounts)
- Understands SEO concepts but values automation and time savings
- Checks results on desktop, generates reports for clients
- Cares about: ranking movement, report delivery, issue detection, client dashboards
- Can tolerate more technical language if it is efficient
- Needs batch operations and campaign switching

**Note:** The current product serves the agency user reasonably well at the data layer. The primary UX gap is for the business owner user. These specs focus primarily on the business owner experience, with agency needs noted where they diverge.

---

## 4. Core Jobs-To-Be-Done

| # | Job | Trigger | Success Condition |
|---|---|---|---|
| 1 | Understand current online visibility | Logging in / checking in | User sees a clear summary of where they stand |
| 2 | Know if things are getting better or worse | After a week or month | User sees trend with a plain-English interpretation |
| 3 | Know what to fix first | When they have time to act | User sees one clear recommended action |
| 4 | See how they rank for key searches | Periodically | User sees position and movement for important searches |
| 5 | Get a report to share with someone | End of month / client meeting | User can generate and send a report in under 2 minutes |
| 6 | Check if their website has problems | After a site update | User sees site issues without needing to run a scan manually |
| 7 | See how they compare to competitors | Quarterly / competitive pressure | User sees clear comparison, not raw data tables |
| 8 | Set up the tool for the first time | Day 1 | User can get from login to first data without support |

---

## 5. Ideal First-Time User Journey

**Entry point:** User logs in for the first time. No campaign exists.

```
Login
  └── Dashboard: no campaign detected
        └── Show "Welcome" intro prompt (not empty KPI cards)
              └── CTA: "Set up your business"
                    └── Onboarding Step 1: Business basics
                    │     - Business name
                    │     - Website URL
                    │     - CTA: "Continue"
                    └── Onboarding Step 2: Your focus area
                    │     - "What type of work do you do?" (dropdown)
                    │     - "What city or area do you serve?" (text or dropdown)
                    │     - CTA: "Continue"
                    └── Onboarding Step 3: Running your first check
                          - Progress indicator
                          - "We're scanning your website and checking where you show up online"
                          - Estimated time: "This takes about 2 minutes"
                          - CTA on complete: "See your results"
                                └── Dashboard: first data visible
```

**Key UX rules for first-run:**
- Never show a form field without explaining what it's for in one sentence
- Never use "campaign," "crawl," "cluster," "keyword snapshot" in visible copy during onboarding
- Always show progress — never leave the user looking at a spinner with no explanation
- First results screen should celebrate: "Your first check is done. Here's what we found."

---

## 6. Ideal Returning User Journey

**Entry point:** User logs in. Campaign already exists. Data is available.

```
Login
  └── Dashboard: active campaign selected
        ├── Trust status bar: "Data updated 2 hours ago"
        ├── KPI summary: ranking position, visibility score, open issues, recent report
        ├── Top change: "Your ranking for 'plumber near me' moved from #14 to #9 this week"
        ├── Recommended action: "You have 3 opportunities to improve. View them →"
        └── Recent activity: last crawl, last rank check, last report
```

**Navigation from dashboard:**
- Rankings → see all keyword positions, movement, history
- Reports → see past reports, generate new one, schedule delivery
- Opportunities → see recommended actions, mark as done
- Settings → update email, notification preferences

**Key UX rules for returning user:**
- Lead with what changed since their last visit
- Never require the user to manually trigger a data refresh if automation is running
- Always show the date/time of the last data update
- If nothing changed, say so: "No major changes this week — you're holding steady"

---

## 7. Recommended Tenant Navigation

**Visible in sidebar (P1 release):**

```
Dashboard         — daily summary, top insights, recommended action
Rankings          — keyword position tracking, movement, history
Reports           — report list, generate, deliver, schedule
Opportunities     — recommended actions from intelligence engine
Settings          — account, notification preferences
```

**Hidden until built (not visible in nav):**

```
Locations         — needs UX design and backend connection
Local Visibility  — needs dedicated workflow and map UX
Site Health       — needs route + data connection
Competitors       — needs comparison UX design
```

**Rules:**
- Never show a nav item that leads to a "coming soon" placeholder or an empty page
- Badge counts must be driven by real data (not hardcoded)
- Active nav item should visually distinguish the current page
- Nav items should be ordered by: most frequently needed first

**Current nav config location:** `dashboard/page.tsx:30` — move to `(product)/nav.config.ts` in a future engineering sprint (P2), not blocking UX work.

---

## 8. Pages That Should Exist Now

These pages should be built for P1 release. All backend APIs are already available.

| Page | Route | Primary API | Priority |
|---|---|---|---|
| Dashboard (redesigned) | `/dashboard` | `/dashboard`, `/campaigns`, `/campaigns/{id}/dashboard` | P0 |
| Rankings | `/rankings` | `/rank/trends`, `/rank/snapshots` | P1 |
| Reports Center | `/reports` | `/reports`, `GET /reports/{id}`, `POST /reports/generate` | P1 |
| Opportunities | `/opportunities` | `/recommendations` | P1 |
| Settings (minimal) | `/settings` | `/auth/me`, tenant config endpoints | P1 |

---

## 9. Pages That Should Be Hidden Until Ready

Do not create placeholder routes for these. Remove from nav. Add back when built.

| Page | Route | Reason Hidden |
|---|---|---|
| Locations | `/locations` | No tenant UI designed. Backend exists. |
| Local Visibility | `/local-visibility` | Partial data only. Needs dedicated map/drilldown UX. |
| Site Health | `/site-health` | Route currently absent. Badge is hardcoded. |
| Competitors | `/competitors` | Backend exists (`competitors.py`), no UI designed. |

**Implementation:** In the nav items array currently defined in `dashboard/page.tsx:30`, add a `hidden: true` field to the `NavItem` type in `types.ts` and filter hidden items in `SidebarNav.tsx`. This way items are preserved in config but not rendered.

---

## 10. Dashboard Redesign Spec

### 10.1 Layout

```
┌─────────────────────────────────────────────────────┐
│ TopBar: [Account badge] [Date range] [Search] [User]│
├─────────────────────────────────────────────────────┤
│ TrustStatusBar: Data freshness signals               │
├──────────────────────────────────────────────────────┤
│                                                      │
│ [Campaign selector dropdown]                         │
│                                                      │
│ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐    │
│ │ KPI: Avg    │ │ KPI: Visi-  │ │ KPI: Open   │    │
│ │ Ranking     │ │ bility Score│ │ Issues      │    │
│ │ Position    │ │             │ │             │    │
│ └─────────────┘ └─────────────┘ └─────────────┘    │
│                                                      │
│ ┌──────────────────────┐ ┌────────────────────────┐ │
│ │ Top Change This Week │ │ Recommended Action     │ │
│ │ (InsightCard)        │ │ (ActionDrawer or card) │ │
│ └──────────────────────┘ └────────────────────────┘ │
│                                                      │
│ ┌──────────────────────┐ ┌────────────────────────┐ │
│ │ Ranking Trend Chart  │ │ Visibility Trend Chart │ │
│ └──────────────────────┘ └────────────────────────┘ │
│                                                      │
│ Recent Activity Timeline                             │
│                                                      │
└─────────────────────────────────────────────────────┘
```

### 10.2 KPI Cards — relabeling spec

| Current label | Proposed plain-English label | Data source |
|---|---|---|
| (unlabeled or internal) | "Your average search position" | `rank/trends` |
| (unlabeled or internal) | "Visibility score" | `campaigns/{id}/dashboard` |
| (unlabeled or internal) | "Website issues found" | `crawl/issues` |
| (unlabeled or internal) | "Last report" | `reports` (most recent) |

Each KPI card should include:
- Current value (large)
- Change from last period (delta, with direction arrow and color)
- One-line plain-English interpretation

### 10.3 Raw forms — demotion plan

The four raw forms currently on the dashboard (campaign create, crawl schedule, rank snapshot, report generate) should be:

- **Campaign create:** Move into the onboarding wizard (new users) and a "Settings" or "Campaign" modal (returning users). Remove from main dashboard surface.
- **Crawl schedule:** Move to a "Run a new check" action in the Actions area or a small "Run scan" button with a confirmation dialog. Do not show crawl type selector to the user — default to "deep" and hide it.
- **Rank snapshot:** Move to the Rankings page as a "Refresh rankings" action.
- **Report generate:** Move to the Reports Center page. Keep a "Create report" shortcut on dashboard as a button that navigates to Reports.

**Safety rule:** Do not delete these forms yet. Move them behind a modal or to a new page. Delete from dashboard only after the new surfaces are live and tested.

### 10.4 Zero state (no campaign)

Show a welcome prompt:
```
"Welcome to InsightOS"
"Let's get your business set up so we can start tracking your online visibility."
[Button: "Set up your business →"]
```

Do not show empty KPI cards. Do not show charts with no data.

### 10.5 Campaign selector

Keep the campaign selector dropdown at the top of the dashboard. For users with one campaign (most SMB users), still show it — it sets context. For agency users with multiple campaigns, this is critical.

---

## 11. Rankings Page Spec

**Route:** `/rankings`
**Backend APIs:** `GET /rank/trends`, `GET /rank/snapshots`

### Layout

```
┌─────────────────────────────────────────────────────┐
│ Rankings                             [+ Add keyword] │
│ [Campaign: My Business ▼]  [Last 30 days ▼]         │
├─────────────────────────────────────────────────────┤
│                                                      │
│ Summary row:                                         │
│  "14 keywords tracked · 3 moved up · 1 moved down"  │
│                                                      │
│ ┌──────────────────────────────────────────────────┐ │
│ │ Keyword          Position  Change   Last checked │ │
│ ├──────────────────────────────────────────────────┤ │
│ │ plumber near me     #9      ▲3      Today       │ │
│ │ emergency plumber   #14     —       Today       │ │
│ │ water heater repair #22     ▼1      Today       │ │
│ └──────────────────────────────────────────────────┘ │
│                                                      │
│ [Ranking Trend Chart — existing component]           │
│                                                      │
└─────────────────────────────────────────────────────┘
```

### Copy rules
- "Position" not "rank" or "SERP position"
- "Moved up" / "Moved down" not "delta" or "+3"
- Show "Today", "Yesterday", "3 days ago" not raw timestamps where possible

### Actions
- "Add keyword" → modal with plain-English prompt: "What do customers search for to find you?"
- "Refresh rankings" → triggers `POST /rank/schedule` with a confirmation and progress state
- Row click → expand to show history chart for that keyword

### Empty state
"You haven't added any search terms yet. Add the phrases your customers use to find businesses like yours."
[Button: "Add your first search term"]

---

## 12. Site Health Page Spec

**Route:** `/site-health` — **HIDDEN until built**

Do not build this page in P1. The badge count in the sidebar is currently hardcoded (not from real data). Remove the badge or hide the nav item entirely.

When built (P2), this page should:
- List crawl-detected issues in plain English ("Your contact page takes too long to load")
- Group by severity (Critical, Important, Minor)
- Show when the last scan ran and offer "Run a new scan"
- Link each issue to a plain-English explanation of why it matters
- Use `GET /crawl/issues` and `GET /crawl/metrics`

---

## 13. Competitors Page Spec

**Route:** `/competitors` — **HIDDEN until built**

Do not build this page in P1. Backend exists (`competitors.py`) but the UX requires a comparison design that does not yet exist.

When built (P2), this page should:
- Show a small set of local competitors in the same service area
- Compare ranking positions for shared keywords
- Show visibility scores side by side
- Use plain-English framing: "These businesses are competing for the same customers"

---

## 14. Reports Center Spec

**Route:** `/reports`
**Backend APIs:** `GET /reports`, `POST /reports/generate`, `GET /reports/{id}`, `POST /reports/{id}/deliver`, `GET /reports/schedule`, `PUT /reports/schedule`

### Layout

```
┌─────────────────────────────────────────────────────┐
│ Reports                  [Create this month's report]│
├─────────────────────────────────────────────────────┤
│                                                      │
│ Scheduled: Monthly · Delivered to: owner@biz.com    │
│ [Edit schedule]                                      │
│                                                      │
│ Past Reports                                         │
│ ┌──────────────────────────────────────────────────┐ │
│ │ March 2026          Generated    [View] [Send]   │ │
│ │ February 2026       Delivered    [View]          │ │
│ │ January 2026        Delivered    [View]          │ │
│ └──────────────────────────────────────────────────┘ │
│                                                      │
└─────────────────────────────────────────────────────┘
```

### "Create this month's report" flow

1. Click button → modal appears
2. Modal: "Create your March 2026 report" — confirm button
3. Show progress state: "Building your report..."
4. On success: "Report ready! [View report] [Send to email]"

Do not show "Month Number" as a number input. Derive current month automatically. If the user needs to select a past month, show a dropdown with month names.

### Report delivery

"Send report to email" → shows email field pre-filled with account email → confirm send.

Remove "Deliver Latest" from the main dashboard. Replace with a link: "Latest report ready → View in Reports"

### Schedule UI

"Automatically send a report every: [Monthly ▼] to [email]"
Save button. Uses `PUT /reports/schedule`.

### Report preview

Use existing `ReportPreview.tsx` component. Sections should be labeled in plain English.

---

## 15. Action Center Spec

**Route:** `/opportunities`
**Backend APIs:** `GET /recommendations`

### Layout

```
┌─────────────────────────────────────────────────────┐
│ Opportunities               5 open · 2 completed    │
├─────────────────────────────────────────────────────┤
│                                                      │
│ ┌──────────────────────────────────────────────────┐ │
│ │ 🔴 High impact                                   │ │
│ │ Your homepage loads slowly                       │ │
│ │ Slow pages rank lower in search results.         │ │
│ │ Fix this to improve your ranking potential.      │ │
│ │                         [View details] [Dismiss] │ │
│ └──────────────────────────────────────────────────┘ │
│                                                      │
│ ┌──────────────────────────────────────────────────┐ │
│ │ 🟡 Medium impact                                 │ │
│ │ Add your business hours to 3 more pages          │ │
│ │ ...                              [View] [Dismiss]│ │
│ └──────────────────────────────────────────────────┘ │
│                                                      │
└─────────────────────────────────────────────────────┘
```

### Card content rules

Each recommendation card must answer:
1. What is the issue (plain English, max 10 words)
2. Why does it matter (plain English, 1 sentence, business impact framing)
3. What to do (one clear action or a link to details)

### Interaction

- "View details" → opens a drawer or detail panel with more information
- "Dismiss" → marks as acknowledged (if API supports) or hides locally for session
- Badge in nav updates when count changes

### P1 simplification

For P1: read-only list with Dismiss action. Do not build approve/run/snooze workflows yet — those require more complex API interaction and UX design.

### Empty state

"No open opportunities right now. We'll notify you when we find ways to improve your visibility."

---

## 16. Settings Spec

**Route:** `/settings`

### P1 minimal scope (do not overbuild)

```
┌─────────────────────────────────────────────────────┐
│ Settings                                             │
├─────────────────────────────────────────────────────┤
│                                                      │
│ Account                                              │
│   Email: owner@mybusiness.com    [Change email]      │
│   Password:                      [Change password]   │
│                                                      │
│ Notifications                                        │
│   Report delivery: Monthly                           │
│   Report email: owner@mybusiness.com                 │
│   [Edit notification settings]                       │
│                                                      │
│ Business                                             │
│   Business name: My Plumbing Co.                     │
│   Website: www.myplumbing.com                        │
│   [Edit business info]                               │
│                                                      │
└─────────────────────────────────────────────────────┘
```

Use `GET /auth/me` for account data. Keep editable fields minimal for P1. Expand in P2.

---

## 17. Empty States

Every page and section must have a designed empty state. Empty states must:
- Explain what the section is for (one sentence, plain English)
- Tell the user what to do to populate it
- Provide a CTA that actually works

### Empty state copy templates

| Page / Section | Heading | Body | CTA |
|---|---|---|---|
| Dashboard — no campaign | "Welcome to InsightOS" | "Let's get your business set up." | "Set up your business" |
| Dashboard — no data yet | "Your first check is running" | "Results will appear here in about 2 minutes." | (spinner, no CTA) |
| Rankings — no keywords | "No search terms tracked yet" | "Add the phrases your customers use to find you." | "Add your first search term" |
| Reports — no reports | "No reports yet" | "Create your first report to see a summary of your progress." | "Create this month's report" |
| Opportunities — none | "No open opportunities" | "We'll alert you when we find ways to improve." | (no CTA needed) |
| Settings — no data | Show pre-filled with known account info | — | — |

### Component to use

`EmptyState.tsx` — already exists. Wire its `onAction` prop to a real handler. Do not ship `EmptyState` with an unhandled button click.

---

## 18. Loading States

Every async operation must show a loading state. Rules:

- Show a loading indicator immediately on action (do not wait for response)
- Show a text label with the loading indicator: "Checking your rankings..." not just a spinner
- For operations > 5 seconds, show an estimated time: "This usually takes about 2 minutes"
- Never show a blank page while data is loading — show skeleton cards or a labeled spinner

### Loading copy templates

| Operation | Loading message |
|---|---|
| Dashboard data loading | "Loading your latest results..." |
| Crawl running | "Scanning your website... this takes 1-2 minutes" |
| Rank snapshot running | "Checking your search positions..." |
| Report generating | "Building your report..." |
| Onboarding step processing | "Setting up your account..." |

---

## 19. Error States

Every operation that can fail must have a designed error state. Rules:

- Never show a raw error message from the API to the user
- Always offer a recovery action (retry, contact support, go back)
- Use plain English: "Something went wrong" not "500 Internal Server Error"
- Log the technical error to the console for debugging — only show the plain version in UI

### Error copy templates

| Error scenario | User message | Recovery CTA |
|---|---|---|
| Login failed | "We couldn't log you in. Check your email and password." | "Try again" |
| Data failed to load | "We couldn't load your results right now." | "Retry" |
| Crawl failed | "Your website scan didn't complete. This can happen if the site was temporarily unavailable." | "Try again" |
| Report generation failed | "We couldn't create your report. Please try again." | "Try again" |
| Network error | "Check your internet connection and try again." | "Retry" |

The `platformApi` client in `platform/api.js` already extracts error messages from `error.message` or `errors[0].message`. Use this pattern consistently and translate API error messages into user-friendly copy before rendering.

---

## 20. Mobile Navigation Pattern

### Problem

`AppShell.tsx:29` hides the sidebar below `xl` breakpoint. No alternate navigation exists.

### Solution: Mobile drawer nav

Add `MobileNav.tsx` component:

```
Mobile viewport (< xl):
┌────────────────────────────────┐
│ [≡] InsightOS    [User avatar] │  ← TopBar with hamburger
├────────────────────────────────┤
│                                │
│  (content area)                │
│                                │
└────────────────────────────────┘

When [≡] tapped:
┌──────────┬─────────────────────┐
│ Dashboard│                     │
│ Rankings │   (content dims)    │
│ Reports  │                     │
│ Opportu- │                     │
│ nities   │                     │
│ Settings │                     │
└──────────┴─────────────────────┘
```

### Implementation rules

- Drawer slides in from left (matches sidebar position on desktop)
- Tap outside drawer to close
- Same `navItems` prop passed to `SidebarNav.tsx` — reuse the same nav component
- Hamburger button: visible only below `xl`, hidden above `xl`
- Does not change desktop layout or any existing responsive breakpoints
- Close drawer on navigation (route change)

### Files to modify (additive)

- New: `(product)/components/MobileNav.tsx`
- Modify: `(product)/components/TopBar.tsx` — add hamburger button, visible below `xl` only
- Modify: `(product)/components/AppShell.tsx` — pass navItems to MobileNav, render MobileNav alongside sidebar

---

## 21. CTA Behavior Requirements

Every button in the product must have a defined behavior. No button should render without an `onClick` handler or a valid `href`.

### Audit of currently inert CTAs

| Component | Button | Required behavior |
|---|---|---|
| `InsightCard.tsx:33` | Action button | Navigate to relevant page or open detail drawer |
| `EmptyState.tsx:23` | Primary CTA | Trigger the relevant setup flow or navigate to setup |
| `TopBar.tsx:25` | Search input | P1: open a search modal or focus a filter; P2: full search |
| `ActionDrawer.tsx` | Action items | Link to recommendations or relevant page section |

### CTA behavior rules

1. If a button triggers a navigation: use `router.push()` or `<Link>` — not `onClick: undefined`
2. If a button triggers an API call: show a loading state immediately, handle success and error
3. If a button is for a feature not yet built: remove the button or replace with a "Coming soon" tooltip — do not render an unhandled click
4. If a button opens a modal: the modal must be built before the button ships

---

## 22. UX Copy Principles

1. **Business first, SEO second.** Frame every metric in business terms before adding technical context. "You show up higher for more searches" before "your average rank improved by 3 positions."

2. **Active voice.** "We found 3 issues on your website" not "3 issues were detected."

3. **Specific over vague.** "Your ranking for 'plumber near me' moved from #12 to #9" not "Your rankings improved."

4. **Short and scannable.** Dashboard copy should be readable in 3 seconds. Insight cards: max 2 lines. KPI deltas: max 5 words.

5. **Honest about limitations.** "Data updates daily" is better than leaving users uncertain about freshness. "This feature is coming soon" is better than a dead link.

6. **Celebrate progress.** When rankings improve, site issues resolve, or a report is delivered — say so clearly: "Great news — you moved up 4 positions this week."

7. **Never blame the user.** Error messages should never imply the user did something wrong unless they clearly did (wrong password). Technical failures are always "we" problems, not "you" problems.

---

## 23. SEO Terms That Need Plain-English Translation

Use these translations consistently throughout all customer-facing copy. Do not use the technical term unless you are also showing the plain-English version.

| Technical term | Plain-English replacement |
|---|---|
| Keyword | "Search term" or "what customers search for" |
| Keyword cluster | "Group of related search terms" (or hide entirely) |
| Crawl / crawl run | "Website scan" |
| Crawl type | Hide from user — default silently |
| Rank snapshot | "Search position check" |
| Location code | "City" or "area you serve" |
| SERP position | "Where you show up in search results" |
| Domain authority | "Website authority score" |
| Local visibility | "How often customers find you online" |
| Organic media value | "Estimated value of your search traffic" |
| Backlinks / citations | "Other websites that mention your business" |
| Campaign | "Your business profile" (for SMB) or "Campaign" (for agency) |
| Intelligence report | "Monthly progress report" |
| Recommendation | "Action to improve your visibility" |
| Entity | "Your business listing" |
| Onboarding | "Setup" |

---

## 24. Component/System Reuse Guidance

The existing component library in `(product)/components/` is well-built. Maximize reuse before building new components.

| Existing component | Reuse for |
|---|---|
| `KpiCard.tsx` | Dashboard KPIs, Rankings summary KPIs |
| `InsightCard.tsx` | Dashboard top change, Opportunities list items (with wired actions) |
| `ChartCard.tsx` | Rankings trend chart, Visibility trend chart |
| `ActionDrawer.tsx` | Dashboard recommended action panel, Opportunity detail drawer |
| `EmptyState.tsx` | All empty states across all pages (with wired CTA) |
| `ReportPreview.tsx` | Reports Center — report detail view |
| `ComparisonTable.tsx` | Rankings page keyword table, future Competitors page |
| `TrustStatusBar.tsx` | All pages — show data freshness |
| `DataFreshnessBadge.tsx` | Data timestamps throughout |
| `SidebarNav.tsx` | Desktop nav and inside MobileNav drawer |

**Before building a new component**, check if an existing one can be extended via props. The component library has good prop patterns — use them.

---

## 25. Safe Implementation Notes for Engineers

These notes are written to reduce regression risk during implementation.

### Do not touch these during UX work

- `app/platform/**` routes — control plane, separate concern
- `app/legacy-dashboard/page.jsx` — legacy, leave in place
- `app/login/page.jsx` — auth flow is working, do not change without explicit reason
- `backend/app/api/v1/` — no backend changes required for P0 or P1 UX work
- `app/layout.jsx` — root layout, leave unless there is a specific reason

### Safest change patterns

| Change type | Approach |
|---|---|
| Adding a new page | New file in `(product)/` route group. Does not affect existing pages. |
| Hiding a nav item | Add `hidden?: boolean` to `NavItem` type in `types.ts`. Filter in `SidebarNav.tsx`. Preserves config. |
| Relabeling copy | String change only. Easiest, lowest risk. |
| Wiring an inert CTA | Add `onClick` handler. If it navigates, use `useRouter`. If it calls API, use `platformApi`. |
| Moving a form | Wrap in a modal or drawer component. Keep the form logic unchanged — only move where it renders. |
| Adding mobile nav | New `MobileNav.tsx` + small additions to `TopBar.tsx` and `AppShell.tsx`. Does not change desktop layout. |

### API client consistency

The dashboard currently uses an inline `fetch` pattern with its own auth/refresh logic, separate from `platformApi` in `platform/api.js`. This is a known divergence.

- For new pages (Rankings, Reports, Opportunities, Settings): use `platformApi` from `platform/api.js`
- Do not refactor the dashboard's inline fetch in the same sprint as UX changes — too much risk
- Plan a fetch consolidation as a dedicated engineering task in P2

### Feature flag recommendation

If the team wants to gate new pages behind a flag before releasing to all users, add a simple environment variable check:

```ts
// Example: only show Rankings page if NEXT_PUBLIC_SHOW_RANKINGS=true
const showRankings = process.env.NEXT_PUBLIC_SHOW_RANKINGS === 'true';
```

This allows internal testing before customer release without nav changes.

### Test before hiding nav items

Before hiding any nav item, verify:
1. No other component links directly to that route via `<Link href="...">` or `router.push()`
2. No API call depends on that page being active
3. The route can be re-enabled by simply unhiding the nav item (no data dependencies)

### Onboarding wizard — safe implementation pattern

Build the wizard as a separate component (`OnboardingWizard.tsx`) that renders conditionally in the dashboard page:

```tsx
// In dashboard/page.tsx
if (campaigns.length === 0 && !isLoading) {
  return <OnboardingWizard onComplete={() => refetchCampaigns()} />;
}
```

This pattern:
- Does not modify the existing dashboard rendering path
- Is easy to test independently
- Can be bypassed by skipping if campaign count > 0
- Can be removed cleanly if the approach changes

---

## Recommended Next Implementation Sequence

Safe order to implement without breaking working functionality:

**Phase 1 — No-risk changes (copy, hide, wire)**
1. Add `hidden?: boolean` to `NavItem` type in `types.ts`
2. Filter hidden items in `SidebarNav.tsx`
3. Set `hidden: true` on Locations, Local Visibility, Site Health, Competitors in nav config
4. Relabel all form field labels on dashboard in plain English (copy only)
5. Wire `EmptyState.tsx` `onAction` to campaign creation scroll or modal trigger
6. Wire `InsightCard.tsx` action buttons to relevant page navigation
7. Add zero-state detection on dashboard: show welcome prompt if `campaigns.length === 0`

**Phase 2 — Onboarding wizard (new component, existing APIs)**
8. Build `OnboardingWizard.tsx` (new component, 3 steps)
9. Integrate with `POST /campaigns`, `POST /crawl/schedule`, `POST /rank/schedule`
10. Render wizard conditionally in dashboard when no campaign exists

**Phase 3 — New pages (additive routes, existing APIs)**
11. Build `app/(product)/reports/page.tsx` using `GET /reports`, `POST /reports/generate`
12. Build `app/(product)/opportunities/page.tsx` using `GET /recommendations`
13. Build `app/(product)/rankings/page.tsx` using `GET /rank/trends`, `GET /rank/snapshots`
14. Enable these nav items (remove `hidden: true`)
15. Build `app/(product)/settings/page.tsx` (minimal)

**Phase 4 — Mobile nav + polish**
16. Build `MobileNav.tsx` drawer component
17. Add hamburger button to `TopBar.tsx` (mobile only)
18. Update `AppShell.tsx` to render `MobileNav` on mobile viewports
19. Wire Opportunities badge count to real `GET /recommendations` count
20. Remove raw forms from dashboard main surface (move to dedicated pages built in Phase 3)
