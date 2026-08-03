# InsightOS Customer Visual System

Version: `customer-visual-system-v2`

This folder is the shared interface contract for every signed-in customer
page. It is designed for a busy local service-business owner. It does not copy
the artwork, layout, or navigation of another SEO product.

## Reading order

Every page follows the same order:

1. purpose and active location;
2. key result;
3. primary chart, map, or comparison;
4. the next useful action;
5. supporting details;
6. optional source, method, and troubleshooting information.

The shared `customerPageOrder` value in `visualSystem.ts` makes that order
testable. The rollout flag is
`NEXT_PUBLIC_CUSTOMER_VISUAL_SYSTEM_V2_ENABLED`; it is on unless explicitly set
to `false`.

## Language contract

Customer copy follows
`backend/app/intelligence/lexicon/service_business_language_guide.md` and the
browser-safe mirror in `truth/customerLanguage.mjs`.

- Lead with the action or business result.
- Prefer short sentences and common words.
- Translate search, data-source, model, and system language.
- Say `We need more information` when a result cannot be supported.
- Put proof and troubleshooting behind `DetailsDisclosure`.
- Never promise rankings, calls, leads, or revenue.

Static copy and AI-written guidance use the same prohibited-phrase checks.

## Original icon family

`ProductIcon` contains the InsightOS line-icon family. It covers every route,
charts, dates, actions, warnings, trends, completed work, information, and
empty states. Icons beside text are decorative; standalone icons require a
`label`. Color is never the only carrier of meaning.

## Shared component inventory

| Need | Component | Required behavior |
| --- | --- | --- |
| Shell and location scope | `AppShell`, `TopBar`, `LocationContext` | Keep business and location visible. Hide healthy diagnostic noise. |
| Page purpose | `ProductPageIntro` | Show an original page icon, short purpose, and one compact start instruction. |
| Owner decision | `OwnerDecisionPanel` | State the current result, business meaning, next action, and optional accessible progress. |
| Section hierarchy | `PageSection` | Group one decision without adding a decorative card. |
| Compact results | `MetricStrip`, `KpiCard` | Show the value, meaning, and semantic trend. |
| Direction | `TrendIndicator` | Use words, an arrow, and green/red/neutral styling together. |
| Historical data | `ChartCard`, `ScopeBar` | Support location, date range, comparison, legend, details, and accessible labels. |
| Missing history | `DataState`, `ChartEmptyState` | Distinguish empty, one point, partial, stale, unsupported, error, and loading states. |
| Comparisons | `ComparisonTable` | Add a short interpretation before the rows. |
| Recommended work | `ActionDrawer` | State the action before supporting proof. |
| Optional proof | `DetailsDisclosure` | Keep methods and technical facts available without leading with them. |
| Loading and no-data | `LoadingCard`, `EmptyState` | Explain what is happening and what the owner can do. |
| Daily guide | `TruthNotice` | Show at most once per page, allow dismissal, and use the shared language filter. |

## Route coverage

The contract applies to Overview, Search Rankings, Local Search, Website
Health, Next Steps, Reports, Data Connections, Locations, Search Value,
Competitors, and Directory Listings. UX11/T30 applies the system first to
Overview and Next Steps. UX12/T31 completes the remaining page-specific
charts, maps, decision summaries, progress visuals, and task flows.

## Visual rules

- Accent orange identifies focus and action, not decoration.
- Green plus an upward arrow means a beneficial change.
- Red plus a downward arrow means a harmful change.
- Neutral uses gray plus a horizontal arrow.
- Borders separate real groups. Do not put every sentence or number in a box.
- A chart must answer a decision. If the data cannot support a chart, use an
  honest `DataState` instead.
- Source freshness belongs in optional details unless it needs attention.
