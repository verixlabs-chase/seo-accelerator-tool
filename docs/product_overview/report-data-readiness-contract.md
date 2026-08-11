# Report Data Readiness Contract

Date: 2026-08-11

## Purpose

The report screen must tell an owner what the next report can prove before the
owner creates or shares it. Missing data is never converted to zero, and a
fresh supporting check cannot hide a stale Google search source.

## API

`GET /api/v1/reports/readiness?campaign_id={campaign_id}`

The endpoint is authenticated, tenant scoped, and organization scoped. A
campaign outside the active organization returns `404`.

The response contains:

- `status`: `ready`, `limited`, or `needs_setup`;
- `can_generate`: currently `true`, because a limited report is more honest
  than silently blocking the owner;
- `warning_count`: non-optional sources that are missing, partial, or stale;
- one entry for Google search results, website checks, tracked searches, and
  optional customer-review data;
- the last saved date, coverage where applicable, a plain-language reason, and
  a direct recovery destination.

## Readiness rules

### Google search results

- `missing`: no saved Search Console daily fact exists.
- `stale`: the newest saved day is more than four days old. This allows for
  Google's normal reporting delay without treating an old connection as fresh.
- `ready`: both the current and equal comparison periods contain at least 24 of
  30 days.
- `partial`: facts exist but one of the two periods has less coverage.

### Website check

- `missing`: there is no completed crawl.
- `stale`: the newest completed crawl is more than 30 days old.
- `ready`: a completed crawl is no more than 30 days old.

### Tracked searches

- `missing`: no customer searches are being tracked.
- `partial`: searches are selected but no position has been saved.
- `stale`: the latest saved position is more than 14 days old.
- `ready`: a recent saved position exists.

### Customer reviews

Review data is optional while Google Business Profile production access is not
available. Its absence never prevents report generation and is labeled
`optional`, not failed.

## Overall state

- `ready`: Google search history is ready and either the website check or
  tracked-search evidence is ready.
- `limited`: at least one core source has usable facts, but the detailed-report
  rule is not met.
- `needs_setup`: no core source has usable facts yet.

## Report source rule

New reports read `search_console_daily_metrics` directly for visits,
appearances, average position, coverage, and Google trend charts. The
`campaign_daily_metrics` rollup remains a fallback only when no direct Search
Console facts exist, preserving older installations and derived intelligence
fields without allowing a lagging rollup to overwrite newer provider facts.

The report snapshot records direct Search Console row counts for both the
current and comparison periods so source selection remains auditable.
