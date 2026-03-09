# WHITE_LABEL_REPORTING_SPEC.md

## 1) Scope

Defines LSOS white-label reporting architecture, data contracts, branding controls, rendering requirements, PDF export, and scheduled email delivery.

## 2) Report Objectives

- Deliver tenant-branded monthly performance reports.
- Aggregate campaign outcomes across all LSOS modules.
- Provide actionable strategy recommendations and next-30-day plan.
- Support automated generation and delivery at production scale.

## 3) Report Structure (Authoritative Section Order)

1. Cover Page
2. Executive Summary
3. Technical Score
4. Ranking Change
5. Competitor Comparison
6. Link Growth
7. Review Growth
8. Content Production
9. Strategy Recommendations
10. Next 30-Day Plan
11. Appendix (methodology, glossary, data confidence)

## 4) Data Sources

Section-to-source mapping:
- Technical Score: `crawl_page_results`, `crawl_runs`, issue severity aggregates.
- Ranking Change: `rankings`, keyword clusters, geo snapshots.
- Competitor Comparison: `competitor_rankings`, competitor gap metrics.
- Link Growth: `backlinks`, outreach outcomes.
- Review Growth: `reviews`, `review_velocity_snapshots`.
- Content Production: `content_assets`, internal link map deltas.
- Strategy Recommendations: `strategy_recommendations`, `intelligence_scores`.
- Next 30-Day Plan: campaign logic outputs + unresolved milestones.

Data freshness policy:
- Freeze reporting window before aggregation.
- Include confidence indicator when data completeness is below threshold.

## 5) Branding Customization

Tenant brand profile fields:
- `brand_name`
- `logo_asset_id`
- `primary_color`
- `secondary_color`
- `accent_color`
- `font_family_header`
- `font_family_body`
- `footer_legal_text`

Branding rules:
- Strict tenant isolation for brand assets.
- Default template fallback when tenant profile incomplete.
- Validate color contrast for accessibility and print quality.

## 6) Logo Handling

Supported formats:
- SVG (preferred), PNG.

Asset constraints:
- Max file size: 2 MB.
- Minimum resolution for raster logos: 1200 px width.
- Background handling: transparent preferred.

Storage and rendering:
- Store in object storage with tenant-scoped paths.
- Pre-generate normalized variants for web/PDF rendering.
- Use signed URLs with short expiry for retrieval.

## 7) Chart Requirements

Rendering library:
- Chart.js or Recharts (frontend), server-side deterministic render for PDF snapshots.

Required charts:
- Technical score trend line (3-12 months).
- Visibility/average position trend with baseline markers.
- Competitor rank share bar/line comparison.
- Backlink acquisition trend by quality tier.
- Review volume and average rating trend.
- Content output vs required quota chart.

Chart standards:
- Include units and time window labels.
- Use tenant palette tokens where legible.
- Export vector-safe or high-resolution raster for PDF.

## 8) HTML Templating

Template engine requirements:
- Versioned templates (`template_version`).
- Componentized sections per report structure.
- Server-side render with strict escaping and sanitization.

Template contract:
- Input:
  - `tenant_id`, `campaign_id`, `report_month`, `branding_profile`, `section_payloads`, `recommendations`
- Output:
  - deterministic HTML string for PDF conversion and browser preview.

Fallback behavior:
- Missing section data renders explicit “Data unavailable” block with reason code.

## 9) PDF Export

Pipeline:
1. Validate aggregate completeness.
2. Render HTML with brand profile.
3. Convert HTML to PDF (headless browser).
4. Validate artifact size/page count/hash.
5. Store artifact and metadata.

PDF requirements:
- Standard size: Letter (US) with configurable A4 option.
- Margin and bleed-safe layout for print.
- Embedded fonts and images.
- Page numbers and footer legal text.

Output metadata:
- `report_id`
- `artifact_url`
- `artifact_sha256`
- `page_count`
- `generated_at`

## 10) Scheduled Email Delivery

Delivery workflow:
1. Resolve recipient list from tenant/campaign settings.
2. Validate report readiness.
3. Queue email delivery task.
4. Track send status and provider response.
5. Retry transient failures with capped policy.

Email content requirements:
- Tenant branding in header/footer.
- Executive summary highlights.
- Secure link to report artifact.
- Optional attachment (size policy controlled by config).

Delivery tracking:
- `queued_at`, `sent_at`, `provider_message_id`, `delivery_status`, `failure_reason`.

## 11) Section Contracts

### 11.1 Technical Score
- Inputs: issue counts by severity, indexability stats, crawl stability.
- Outputs: score (0-100), trend, top blockers, remediation priority list.

### 11.2 Ranking Change
- Inputs: keyword-level positions by geo and cluster.
- Outputs: net movement, visibility trend, top winners/decliners.

### 11.3 Competitor Comparison
- Inputs: competitor snapshots and overlap terms.
- Outputs: comparative rank share, gap topics, threat/opportunity notes.

### 11.4 Link Growth
- Inputs: backlink acquisitions, quality tiers, placement status.
- Outputs: net new live links, quality distribution, attribution to campaigns.

### 11.5 Review Growth
- Inputs: review volume, average rating, sentiment trends.
- Outputs: velocity score, month-over-month delta, review risk indicators.

### 11.6 Content Production
- Inputs: produced/published assets and quotas.
- Outputs: completion percentage, type breakdown, publishing cadence trend.

### 11.7 Strategy Recommendations
- Inputs: campaign intelligence scores and anomalies.
- Outputs: prioritized actions with rationale and expected impact.

### 11.8 Next 30-Day Plan
- Inputs: month-stage logic + unresolved milestones.
- Outputs: dated execution plan, owners, dependencies, expected outcomes.

## 12) Scaling and Performance

Targets:
- Generate 100+ monthly reports in scheduled batch windows.
- Keep p95 report generation latency under 5 minutes per report.

Controls:
- Dedicated reporting queue and worker autoscaling.
- Pre-aggregation cache for common KPI windows.
- Prioritized processing for overdue campaign reports.

## 13) Security and Compliance Controls

- Tenant-scoped data and branding retrieval only.
- Signed artifact URLs with expiry.
- Audit events for generate/download/delivery operations.
- PII minimization in report payloads and logs.

## 14) Failure Handling

Failure classes:
- Data completeness failure.
- Template rendering failure.
- PDF conversion failure.
- Email provider failure.

Handling policy:
- Retry transient failures.
- Dead-letter terminal failures with operator triage.
- Persist partial diagnostics for replay.

## 15) APIs and Tasks Dependencies

Key APIs:
- `POST /api/v1/reports/generate`
- `GET /api/v1/reports`
- `GET /api/v1/reports/{id}`
- `POST /api/v1/reports/{id}/deliver`

Key tasks:
- `reporting.freeze_window`
- `reporting.aggregate_kpis`
- `reporting.render_html`
- `reporting.render_pdf`
- `reporting.send_email`

This document is the governing white-label reporting contract for LSOS.
