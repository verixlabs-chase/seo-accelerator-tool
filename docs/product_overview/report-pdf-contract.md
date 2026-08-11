# Client-ready report PDF contract

## Purpose

Downloaded reports must tell the same story as the authenticated report preview
without turning into a raw metric dump. The PDF is an artifact of the frozen
RPT1 report snapshot; rendering must never recalculate live facts or silently
change the stored comparison.

## Required reading order

1. Business and reporting period.
2. Plain-language result headline and summary.
3. Results at a glance, including missing measurements.
4. Current-versus-earlier trend charts with written descriptions.
5. Verified improvements, risks, completed work, and measured results.
6. Numbered next actions with steps and the measurement used to check success.
7. Source, last-update, and coverage appendix.
8. Snapshot version, snapshot ID, and evidence disclaimer.

## Visual and accessibility rules

- Use letter-sized pages with consistent margins, page numbers, and VerixLabs
  document metadata.
- Use original InsightOS orange for the current period and dashed blue for the
  earlier period. Never rely on color alone; every chart includes text labels
  and a written explanation.
- Keep headings with their first meaningful content and prevent empty pages.
- Keep each numbered action card together whenever it fits on one page.
- Preserve extractable text, logical source order, English-language metadata,
  and PDF outline bookmarks for major sections.
- Show missing data as `Not measured` and show partial or unavailable coverage
  plainly.
- Replace unsupported typography with safe ASCII equivalents so customer and
  location names never render as black boxes.
- Do not claim PDF/UA certification until a dedicated conformance audit and
  tagged-PDF implementation have passed.

## Determinism and security

- HTML and PDF files render only from the persisted report snapshot.
- Regeneration preserves the snapshot hash and does not query live providers.
- Private artifact storage, authenticated downloads, expiring links, and
  revocation remain governed by the existing RPT1 delivery contract.
- PDF metadata may contain the business/location report title but no API keys,
  session values, recipient secrets, or provider credentials.

## Release checks

- Report tests parse the PDF and require multiple non-empty pages, metadata,
  language, outline navigation, action text, charts, and source appendix text.
- A representative report is rendered to PNG with Poppler and every page is
  inspected for clipping, overlaps, unreadable labels, empty pages, and broken
  section transitions before release.
