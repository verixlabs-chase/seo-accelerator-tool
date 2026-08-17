# Owned-site index and sitemap evidence

## Purpose

SEO2A answers a narrow owner question: **Can Google find and keep this
location's important pages?** It does not replace the website crawler and it
does not claim that sitemap submission, ranking presence, crawlability, or a
valid canonical are the same as indexation.

## Sources and meaning

- Google Search Console URL Inspection supplies Google's saved index result for
  an owned URL. It is stored with the coverage reason, robots state, indexing
  state, page-fetch state, Google-selected canonical, user-selected canonical,
  last crawl time, and returned sitemap/referring URLs.
- Google Search Console Sitemaps supplies processing state, errors, warnings,
  submission totals, and observation times. The deprecated `indexed` response
  field is discarded and must never be used in a calculation or claim.
- The InsightOS website scan supplies the live HTTP result and current
  crawl-derived indexability signal. A conflict between the live scan and
  Google's saved result is shown as a conflict, not silently resolved.

Official provider contracts:

- <https://developers.google.com/webmaster-tools/v1/urlInspection.index/inspect>
- <https://developers.google.com/webmaster-tools/v1/sitemaps/list>
- <https://developers.google.com/webmaster-tools/v1/sitemaps>
- <https://developers.google.com/webmaster-tools/limits>

## Collection guardrails

- The refresh is tenant, organization, campaign, and connection scoped.
- Only an active Search Console mapping for the selected campaign may run.
- The latest crawl supplies priority URLs; the campaign homepage is the safe
  fallback before the first crawl.
- A request checks 10 URLs by default and cannot check more than 25. This keeps
  one user action bounded well below the provider's per-site daily inspection
  quota.
- Sitemap health is read once per refresh. A sitemap failure stops the refresh;
  an individual URL failure is recorded and does not discard successful URLs.
- Refresh errors use customer-safe language while durable connection metadata
  records counts and the last refresh time.

## Stored evidence

`url_inspection_snapshots` stores the latest owned-URL evidence per campaign and
URL. `search_console_sitemap_snapshots` stores the latest sitemap evidence per
campaign and sitemap URL. Both tables carry tenant and organization keys,
foreign keys to the campaign/connection, PostgreSQL RLS, source contract
versions, and observed timestamps.

This first slice stores the latest result rather than a complete historical
inspection ledger. Trend claims therefore remain disabled until a later slice
adds immutable history and enough repeated observations.

## UI contract

Every displayed problem includes:

- the affected URL;
- plain-language evidence;
- an explicit source and checked time;
- severity and deterministic confidence;
- one supported next action.

The default view shows at most five priority findings. The explanatory note
states that URL Inspection is Google's saved index information, not a live
test, and that sitemap submissions are not proof of indexation.

## Non-claims and deferred work

SEO2A does not yet claim complete-site coverage, live production proof,
redirect-chain analysis, duplicate or orphan discovery, structured-data
validation, cannibalization, content decay, SERP feature tracking, entity-gap
analysis, or Bing coverage. Those remain separately testable SEO2 slices.
