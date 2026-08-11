# Report Portfolio Comparison Contract

## Purpose

Multi-location reporting helps an owner see which locations need attention
without blending unlike businesses, dates, or evidence. The comparison reads
the latest frozen RPT1 report snapshot for each campaign in the signed-in
organization. It does not query live providers or recalculate a saved report.

## Comparison rules

1. Every location remains a separate row with its own campaign, location,
   report, period, snapshot hash, source freshness, metrics, wins, risks, and
   next action.
2. Totals are never added across locations. Website visits, appearances,
   rankings, reviews, and health measurements retain their location scope.
3. A location is comparable only when its latest report uses a supported RPT1
   snapshot and passes the saved integrity-hash check.
4. A direct comparison or recommended focus requires at least two comparable
   locations with identical current and prior date ranges.
5. When dates differ, the locations may still be displayed, but the product
   must explain the mismatch and must not name a leader or laggard.
6. Missing, legacy, and invalid reports remain visible with a specific recovery
   instruction instead of being converted to zero.

## Customer presentation

- Lead with the number of locations ready to compare.
- Use one compact table with familiar business labels.
- Show the current value and plain-language direction for each metric.
- Use `Improved`, `Needs attention`, `About the same`, and `No full comparison`
  instead of exposing internal calculation labels.
- Let the owner switch directly to any location for its full report evidence.
- A `Start with` location may be shown only when aligned snapshots contain
  saved risks; the explanation must cite the saved risk count.

## Security and determinism

- The endpoint is tenant- and organization-scoped through the authenticated
  user context.
- Cross-organization campaigns and reports are excluded by the report query.
- Invalid snapshot hashes expose no metrics in the comparison response.
- The response declares `totals_are_combined: false` and identifies its source
  contract as `latest_frozen_report_snapshot_per_location`.

## Release checks

- Two aligned, valid reports appear as two distinct comparable rows.
- A location without a report remains visible and does not block other rows.
- Tampering with a saved snapshot removes that location from comparison.
- The frontend never presents blended totals.
- The production page can switch from a comparison row to the selected
  location's detailed report.
