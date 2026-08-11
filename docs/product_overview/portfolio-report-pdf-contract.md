# All-Location PDF Report Contract

## Purpose

The all-location PDF gives an owner or manager one shareable view of multiple
business locations without combining unrelated business results into a single
total.

## Source of truth

- The download uses the latest integrity-checked RPT1 report snapshot for each
  included campaign.
- Every included location must use the same current and comparison dates.
- At least two matching location reports are required.
- The PDF renderer does not query live providers, recalculate metrics, replace
  missing data with zero, or infer an outcome.
- The portfolio document receives its own deterministic hash from the exact
  component reports, organization identity, period, and bounded brand record.
- The appendix records every component report ID, generated time, and complete
  snapshot hash so the document's lineage can be audited.

## Customer-facing content

The PDF contains:

1. A summary showing the included location count, shared dates, and the saved
   location that needs attention first.
2. A side-by-side table for visits from Google, times shown, average Google
   position, tracked-search position, and items needing attention.
3. Visual comparisons for visits and appearances. When more than 12 locations
   have a value, the chart labels itself as showing the 12 highest saved values;
   the table still lists every included location.
4. A detail section for every location with saved results, wins, risks, and a
   plain-language next action.
5. A source-record appendix with the component report lineage and the
   all-location document hash.
6. The total organization location count and a named recovery list for every
   location that could not be included, so a missing report is never mistaken
   for zero performance.

## Branding boundary

The paid-plan report identifies:

- InsightOS as the product;
- VerixLabs as the publisher; and
- the current organization in a `Prepared for` label.

This is customer-specific document identity, not white labeling. Custom logos,
custom colors, custom domains, and removal of InsightOS or VerixLabs branding
remain Enterprise controls and must be implemented behind plan enforcement.

## Failure behavior

The download returns a conflict response instead of a misleading PDF when:

- fewer than two location snapshots pass integrity validation;
- report periods do not match; or
- a component snapshot changes or fails its integrity check between comparison
  and document assembly.

Missing, legacy, and invalid locations remain visible in the on-screen
comparison with recovery guidance, but are not silently inserted into the PDF.

## Security

- The endpoint requires an authenticated tenant administrator.
- Organization scope is taken from the authenticated session, never from a
  caller-supplied organization ID.
- Every component report is resolved through the existing tenant and
  organization report guard.
- The response is marked private and non-cacheable.
