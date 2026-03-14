# UI Validation and Polish Sweep
**Date:** 2026-03-14
**Branch:** claude/qa-ui-polish-sweep-e40bo
**Reviewer:** Claude (QA / UI Polish Lead)

---

## 1. Executive Summary

The product is substantially built and functional as a dark-themed, data-dense local SEO dashboard. The design system is coherent — one consistent token set, shared components, uniform eyebrow/heading/summary patterns, and a working AppShell that wraps all product pages. The major surfaces (Dashboard, Rankings, Reports, Opportunities, Local SEO, Site Health) all exist and are wired to real API endpoints.

However, there are a collection of UI polish, copy consistency, semantic, and empty-state issues that make the product feel slightly stitched-together and operator-facing rather than user-facing. None are architectural — all are presentation-layer. This sweep identifies the issues and applies safe, low-risk fixes without changing behavior.

---

## 2. Current Product Maturity Snapshot

| Dimension | Status |
|---|---|
| Design system consistency | Good — shared tokens, components, color palette |
| Page-level structure | Good — consistent ProductPageIntro, TrustStatusBar, KpiCards |
| Navigation | Good — sidebar + mobile nav work, active state is correct |
| Loading states | Functional but minimal |
| Empty states | Present on all pages, functional |
| Error states | Present but visually inconsistent (missing rounded corners) |
| Copy quality | Mostly good, but internal/operator language leaks in several places |
| Mobile responsiveness | Partially handled, some concerns with TopBar action-heavy layout |
| Accessibility | Minimal — missing focus rings on inputs, h1 duplication in sidebar |
| Build health | Lint passes clean (0 errors, 0 warnings) |

---

## 3. Pages Reviewed

- `frontend/app/page.jsx` — Home / landing page
- `frontend/app/login/page.jsx` — Sign in
- `frontend/app/(product)/dashboard/page.tsx` — Main dashboard
- `frontend/app/(product)/components/OnboardingWizard.tsx` — Setup wizard
- `frontend/app/(product)/rankings/page.tsx` — Rankings
- `frontend/app/(product)/reports/page.tsx` — Reports
- `frontend/app/(product)/opportunities/page.tsx` — Opportunities
- `frontend/app/(product)/local-visibility/page.tsx` — Local SEO
- `frontend/app/(product)/site-health/page.tsx` — Technical Health
- All shared components in `frontend/app/(product)/components/`
- `frontend/app/(product)/nav.config.ts`
- `frontend/app/layout.jsx`

---

## 4. What Is Working Well

1. **Consistent design token usage** — Color palette, border colors, shadow values, and spacing are applied uniformly across all pages.
2. **ProductPageIntro component** — Every product page uses the same eyebrow/heading/summary intro pattern. Consistent and clean.
3. **TrustStatusBar** — Consistent top-of-page signal strip. Works well as a quick-read data freshness layer.
4. **KpiCard grid pattern** — All pages use the 4-column KpiCard grid consistently. Values, changeLabels, and summaries follow the same structure.
5. **Summary card pattern** — All product pages use the 2-column summary card (left: title + body, right: "what to do next" box). Coherent and readable.
6. **EmptyState coverage** — Every page has an EmptyState for the no-data case, and they all route back to the dashboard as a recovery path.
7. **LoadingCard presence** — Every page shows a loading state during data fetch.
8. **OnboardingWizard** — 3-step wizard is solid: step indicator, task list, error handling, async scan launch. The UX flow is clear.
9. **Mobile nav** — Drawer opens/closes correctly, closes on route change, overlay backdrop present.
10. **AppShell layout** — Sidebar + TopBar + TrustStatusBar + main content structure is well-organized.
11. **Error handling** — All pages catch fetch errors and display them (though with a visual inconsistency noted below).
12. **Nav config** — Hidden items (Settings, Locations, Competitors) are cleanly filtered from the nav. Coming-soon items are marked correctly.
13. **Opportunities / action controls** — ActionDrawer is used well to surface recommendation evidence and actions. Approval flow is present.

---

## 5. UI / UX Problems Found

### P1 — EmptyState icon shows "LS" (internal abbreviation)
**File:** `components/EmptyState.tsx:16`
The centered icon box renders hardcoded text "LS" — likely an abbreviation for "Local SEO." This is meaningless to users and looks like an unfinished placeholder.

### P2 — InsightCard exposes raw tone value as a visible badge
**File:** `components/InsightCard.tsx:29`
The card renders `{tone}` directly in a badge: shows "info", "warning", "danger", "success" as user-visible text. These are internal state labels, not user-facing copy.

### P3 — LoadingCard misused as empty state for "No recent reviews"
**File:** `local-visibility/page.tsx:537`
When no reviews exist, the code renders `<LoadingCard title="No recent reviews" summary="No reviews have been captured yet for this business." />`. A LoadingCard semantically implies ongoing loading — using it for a stable empty state is confusing. Users may interpret this as the data still loading.

### P4 — Login page copy: "Need a different entry point?"
**File:** `login/page.jsx:98`
"Need a different entry point?" is operator/internal language. It doesn't map to anything a real end user would understand or want. The only action is "Back to home" — the copy should match that intent.

### P5 — SidebarNav "Operating principle" card is internal tooling language
**File:** `components/SidebarNav.tsx:83–90`
A card at the bottom of every sidebar reads: *"Every screen should explain what changed, why it matters, and what to do next."* This is a product principle for the development team, not UI content for users. It should not appear in the shipped UI.

### P6 — SidebarNav uses `<h1>` creating duplicate h1 per page
**File:** `components/SidebarNav.tsx:36`
The sidebar renders `<h1>` for the workspace title. Every product page also renders `<h1>` via `ProductPageIntro`. Multiple `h1` elements on one page is an accessibility problem and a heading hierarchy issue.

### P7 — Error and notice banners missing `rounded-md`
**File:** All product pages — `rankings/page.tsx:424`, `reports/page.tsx:447`, `local-visibility/page.tsx:367`, `site-health/page.tsx:503`, and corresponding notice banners
Inline error/notice `<section>` elements are missing `rounded-md` class, making them look visually broken compared to every other card in the UI which has `rounded-md`.

### P8 — ActionDrawer uses "Action drawer" as the eyebrow label
**File:** `components/ActionDrawer.tsx:21`
The eyebrow reads "Action drawer" — this is a component name, not UI copy. Users see this label and it conveys nothing about what the panel means for them.

### P9 — TopBar search field is non-functional decorative UI
**File:** `components/TopBar.tsx:38`
A div styled as a search input reads "Search pages, keywords, or locations" but has no click handler, no state, and no interaction. It looks like a real input but does nothing. This erodes trust if users try to use it.

### P10 — TopBar "Alerts" and "Help" buttons are non-functional stubs
**File:** `components/TopBar.tsx:46–51`
Both buttons render when no `actions` prop is provided (i.e., on pages that don't pass `topBarActions`). They have `title="Coming soon"` but no other indication of non-functionality. Only visible on dashboard-equivalent views.

### P11 — ComparisonTable lacks eyebrow label (inconsistent with other sections)
**File:** `components/ComparisonTable.tsx:24`
The ComparisonTable only renders an `h3` title, skipping the eyebrow `<p>` that every other section/card uses. This creates a visual inconsistency when it appears alongside other cards.

### P12 — "Keyword table" section heading in rankings
**File:** `rankings/page.tsx:589`
The section eyebrow reads "Keyword table" — this is a data-model term. The heading already says "Which search terms improved or dropped." The eyebrow should match the user-facing pattern.

### P13 — MapCard has hardcoded "Local visibility" eyebrow
**File:** `components/MapCard.tsx:15`
The eyebrow text is hardcoded to "Local visibility" regardless of context. This is fine where it's used but could cause confusion if MapCard is reused elsewhere.

---

## 6. Visual Consistency Problems

1. **Error/notice banners missing `rounded-md`** — Described in P7 above. All other cards use `rounded-md`.
2. **ComparisonTable missing eyebrow** — Described in P11 above.
3. **InsightCard tone badge styling** — The badge uses `border-[#26272c] bg-white/[0.03]` rather than a tone-appropriate color, making it look disconnected from the card tone.
4. **EmptyState "LS" icon** — Out of place with the rest of the design. Other icons use Recharts or inline SVG.
5. **SidebarNav workspace title uses h1** — Breaks heading hierarchy.

---

## 7. Copy / Messaging Problems

| Location | Current Copy | Problem | Fix |
|---|---|---|---|
| `login/page.jsx:98` | "Need a different entry point?" | Internal/technical language | "Not your workspace?" or just "← Back" |
| `SidebarNav.tsx:86` | "Operating principle" card body | Dev-team principle, not user content | Remove or replace |
| `ActionDrawer.tsx:21` | "Action drawer" | Component name as user-visible eyebrow | "Recommended action" |
| `InsightCard.tsx:29` | Raw tone value badge | Shows "info", "warning" etc. | Remove or map to user-friendly label |
| `EmptyState.tsx:16` | "LS" icon text | Internal abbreviation | Replace with neutral icon |
| `rankings/page.tsx:589` | "Keyword table" eyebrow | Data-model term | "Search terms" |
| `reports/page.tsx:534` | "Report month number" label | Confusing field label | "Report period" |

---

## 8. Layout / Hierarchy Problems

1. **Dual h1 per page** — SidebarNav's `h1` and ProductPageIntro's `h1` both exist on every product page. ProductPageIntro is the correct page `h1`; the sidebar's should be a `p` or `span`.
2. **ProductPageIntro heading size** — `text-4xl` / `text-[3.25rem]` is very large for an interior product page. The home page also uses `text-4xl`/`text-5xl`. Interior pages should differentiate. This is lower priority to fix.
3. **TopBar decorative search bar** — Wastes 260px of top-bar horizontal space on mobile with a fake input.

---

## 9. Loading / Empty / Error State Problems

1. **LoadingCard used for empty state** — `local-visibility/page.tsx:537` uses LoadingCard for "No recent reviews" which is a stable empty state, not a loading state. Should use a simple empty message.
2. **Error banners not rounded** — Described in P7. Makes error states look visually broken.
3. **Notice banners not rounded** — Same issue.
4. **LoadingCard has no animation** — Currently it's a static text box with no visual loading indicator (no spinner, no shimmer). This is borderline — it's minimal but functional. Not fixing in this sweep since adding animation requires care.

---

## 10. Interaction / CTA Problems

1. **TopBar fake search input** — Has no interaction at all. Should have a `cursor-not-allowed` or `opacity-60` treatment, or a `title="Coming soon"` attribute, to signal it's not active.
2. **TopBar "Alerts"/"Help" buttons** — Have `title="Coming soon"` tooltip, but no visual difference from active buttons. Should have reduced opacity or a disabled style.
3. **OnboardingWizard "Continue" button on step 1** — Missing `w-full` to match the consistent full-width button pattern used throughout the form. (Step 2 also has `flex gap-3` button layout — different from step 1. Acceptable as designed.)

---

## 11. Mobile / Responsive Problems

1. **TopBar with custom `topBarActions`** — When pages pass `topBarActions` (Rankings, Reports, Local SEO, Site Health), the top bar has both the left info cluster AND the right action cluster, which on small screens creates a very crowded layout. The campaign select + refresh + "Open dashboard" can wrap awkwardly.
2. **Rankings keyword table** — The table has 6 columns with full text in the "What to watch" column. On mobile, this requires horizontal scrolling which is handled by `overflow-x-auto` — this is acceptable.
3. **Mobile nav overlay** — Works correctly. No issues found.

---

## 12. Safe Fixes To Apply Now

The following are confirmed safe, additive, or presentation-only changes:

| # | File | Fix |
|---|---|---|
| F1 | `components/EmptyState.tsx` | Replace "LS" icon text with an SVG icon (simple magnifying glass or check mark) |
| F2 | `components/InsightCard.tsx` | Remove raw tone badge (the tone is already communicated by background color) |
| F3 | `local-visibility/page.tsx` | Replace LoadingCard for empty reviews with a simple empty state message |
| F4 | `login/page.jsx` | Fix "Need a different entry point?" copy |
| F5 | `components/SidebarNav.tsx` | Remove "Operating principle" card from sidebar |
| F6 | `components/SidebarNav.tsx` | Change sidebar `h1` to `p` to fix heading hierarchy |
| F7 | All product pages | Add `rounded-md` to error and notice banner `<section>` elements |
| F8 | `components/ActionDrawer.tsx` | Change eyebrow from "Action drawer" to "Recommended action" |
| F9 | `components/TopBar.tsx` | Add `cursor-not-allowed opacity-50 pointer-events-none` to fake search input |
| F10 | `components/TopBar.tsx` | Add disabled styling to "Alerts"/"Help" stub buttons |
| F11 | `rankings/page.tsx` | Change "Keyword table" eyebrow to "Search terms" |
| F12 | `reports/page.tsx` | Change "Report month number" label to "Report period" |

---

## 13. Risky Issues To Leave Alone For Now

| Issue | Reason Not Fixed |
|---|---|
| ProductPageIntro `h1` heading sizes | Touching heading size affects all pages; visual change risk without benefit to function |
| TopBar search bar — make it functional | Requires new search state, routing, and API endpoint |
| TopBar avatar "VA" — make it dynamic | Requires user context plumbed from auth/me |
| TopBar "Alerts"/"Help" — make them functional | Requires new feature implementation |
| InsightCard tone badge styling improvement | Low priority cosmetic change beyond removing badge |
| ComparisonTable eyebrow pattern | Requires checking how ComparisonTable is used across all pages to ensure no visual regression |
| OnboardingWizard step 1 button width | Minor, not user-blocking |
| MapCard hardcoded "Local visibility" eyebrow | Currently only used in one place; correct in context |
| Mobile TopBar crowding with topBarActions | Requires layout redesign of the top bar responsive behavior |

---

## 14. Validation Results

| Check | Result |
|---|---|
| Frontend lint (`next lint`) | ✅ 0 errors, 0 warnings |
| Frontend dev server starts | ✅ Confirmed in dev log — ready in 1189ms |
| `/login` compiles and loads | ✅ Confirmed (200, 677ms) |
| `/dashboard` compiles and loads | ✅ Confirmed (200, 895ms) |
| Auth flow (localStorage tokens) | ✅ Correct implementation in login page |
| Nav active state | ✅ `buildProductNav` correctly marks `pathname === item.href` |
| Mobile nav close on route change | ✅ `useEffect` on `pathname` closes drawer |
| EmptyState recovery action (router.push) | ✅ All pages route back to `/dashboard` |
| Campaign selector persistence | ✅ Correct pattern across all pages |
| Error boundary coverage | ✅ All pages catch and display errors |

---

## 15. Recommended Small Fix Set

Applied in this sweep (see F1–F12 above):

1. **EmptyState icon** — replaced "LS" with a clean SVG magnifying glass icon
2. **InsightCard** — removed raw tone badge that exposed internal state labels
3. **Local Visibility empty reviews** — replaced LoadingCard misuse with a proper empty message
4. **Login copy** — fixed "Need a different entry point?" to cleaner copy
5. **Sidebar "Operating principle"** — removed internal dev principle card from user UI
6. **Sidebar h1** — changed to `p` tag to fix heading hierarchy
7. **Error/notice banners** — added `rounded-md` across all product pages
8. **ActionDrawer eyebrow** — changed "Action drawer" to "Recommended action"
9. **TopBar fake search** — added non-interactive styling
10. **TopBar stubs** — added disabled visual treatment to Alerts/Help buttons
11. **Rankings eyebrow** — changed "Keyword table" to "Search terms"
12. **Reports field label** — changed "Report month number" to "Report period"

---

## 16. Final Recommendation

**The current UI is stable enough for the next feature phase.** The core product surfaces are built, wired, and consistent enough for real use. The fixes applied in this sweep remove the most visible internal/operator artifacts and tighten the visual consistency of states.

What remains:
- The TopBar's fake search and stub buttons are a known gap that needs a product decision before engineering work begins
- Mobile TopBar layout under heavy `topBarActions` may need design attention before mobile launch
- The heading hierarchy (`h1` in ProductPageIntro vs sidebar) is now fixed — previously it produced two `h1` elements per page

After this sweep, the product should feel meaningfully cleaner and less like internal tooling for a first-time user looking at it fresh.
