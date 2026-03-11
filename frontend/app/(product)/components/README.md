# Product Design System

This folder defines the UI primitives and design contract for the customer-facing Local SEO Operating System.

## 1. Global design system

### Color tokens

- Background: `#070b16`
- Surface 1: `rgba(11, 18, 32, 0.88)`
- Surface 2: `rgba(18, 26, 46, 0.92)`
- Surface 3: `rgba(28, 36, 66, 0.96)`
- Accent: indigo `#6366f1`, violet `#8b5cf6`
- Semantic: green `#22c55e`, yellow `#facc15`, red `#f87171`, blue `#38bdf8`

Defined in [design-tokens.ts](/home/verixlabs/SEO%20Accelerator%20Tool/frontend/app/(product)/components/design-tokens.ts).

### Typography scale

- Display: page titles and hero metrics
- Hero metric: headline KPI values
- Metric: standard KPI cards
- Title: card titles
- Section: uppercase system labels
- Body: explanatory copy
- Caption: secondary meta text

### Spacing system

- Page shell: `px-4 md:px-6 xl:px-8`
- Standard card padding: `p-5 md:p-6`
- Section gap: `gap-6`
- Grid gap: `gap-5`

### Surface styles

- `surfaceStyles.app`: dark operating-system canvas
- `surfaceStyles.shell`: app shell container
- `surfaceStyles.card`: default premium card
- `surfaceStyles.cardElevated`: highlighted or flagship card
- `surfaceStyles.cardSubtle`: supporting surface

## 2. UI philosophy

The interface should always answer:

1. What changed
2. Why it matters
3. What to do next

Rules:

- charts explain movement instead of dumping data
- insight text lives inside cards, not below the page
- filters are secondary to narrative
- trust states stay visible globally
- premium means calm, not dense

## 3. AppShell layout

### Structure

- Left sidebar navigation
- Top bar
- Trust status strip
- Scrollable content region

### Responsive behavior

- desktop: persistent sidebar
- tablet/mobile: AppShell should later collapse sidebar into a sheet
- trust strip remains visible above content

Primary primitive: [AppShell.tsx](/home/verixlabs/SEO%20Accelerator%20Tool/frontend/app/(product)/components/AppShell.tsx)

## 4. Card system architecture

The card system is the product grammar.

### Core card roles

- `KpiCard`: headline metric + short interpretation
- `InsightCard`: what changed and why it matters
- `ChartCard`: chart + explanatory framing
- `MapCard`: flagship geo-visual surface
- `ActionDrawer`: decision and execution surface
- `ReportPreview`: report narrative block
- `ComparisonTable`: structured comparison for portfolio or competitor views
- `EmptyState`: calm, high-clarity no-data state

### Usage pattern

- top of page: KPI cards
- middle: chart or map cards
- right rail or drawer: insight and action cards
- bottom: comparison and report artifacts

## 5. Tailwind styling patterns

These components use Tailwind-style class contracts as the intended design language:

- glass surfaces with low-contrast borders
- indigo/violet glow for focus and flagship states
- rounded corners between `20px` and `30px`
- minimal shadows with soft blur
- strong spacing and typography hierarchy

The current repo is not yet fully Tailwind-enabled. This folder defines the styling contract so the product screens can be built against it cleanly.

## 6. Usage examples

### App shell

```tsx
<AppShell
  navItems={navItems}
  trustSignals={trustSignals}
  accountLabel="Austin Roofing"
  dateRangeLabel="Last 30 days"
>
  <div className="grid gap-5 xl:grid-cols-4">
    <KpiCard
      label="Visibility score"
      value="72"
      changeLabel="+8%"
      summary="Visibility expanded after review velocity improved."
    />
  </div>
</AppShell>
```

### Insight plus action

```tsx
<div className="grid gap-5 xl:grid-cols-[1.3fr_0.7fr]">
  <ChartCard
    title="Ranking momentum"
    summary="Two high-intent keyword clusters recovered this week."
    chart={<div className="h-64 rounded-2xl bg-white/5" />}
  />
  <ActionDrawer
    title="Strengthen service page links"
    summary="Internal linking remains the clearest technical lever."
    evidence={[
      "Dropped pages have weaker internal link depth.",
      "High-intent keywords recovered after related page updates.",
    ]}
  />
</div>
```

## 7. Implementation notes

- Prefer `Mapbox` for local visibility maps.
- Prefer `Recharts` for line, bar, and distribution charts.
- Keep summary text in the component API rather than bolting it on per-page.
- Do not build dense admin-style tables into the core customer experience.
