# Crawl-derived website integrity evidence

## Purpose

SEO2B turns the InsightOS website scan into evidence that can support specific,
plain-language repair work. It answers questions such as:

- Does a link on this website lead to a broken page?
- Are two indexable pages serving the same visible copy?
- Is a page disconnected from the rest of the website?
- Does a preferred-page setting point to a page the scan could not find?
- Does a page take more than one redirect to reach its destination?
- Can the page's JSON-LD search-result details be parsed?

These are crawl observations. They are not Google indexing verdicts, ranking
factors, traffic forecasts, or proof that a repair will improve rankings.
Google-owned index evidence remains a separate SEO2A source.

## Stored evidence

Each page result now preserves:

- requested and final URL;
- every HTTP redirect hop returned by the HTTP client;
- resolved canonical URL, including valid relative canonicals;
- a hash and word count of sufficiently substantial normalized visible copy;
- internal-link count and a tenant-scoped source-to-target link graph;
- JSON-LD types found and whether every JSON-LD block parsed successfully.

`crawl_internal_links` records the run, source page, normalized target URL, and
matched target page when that target was scanned. PostgreSQL row-level security,
tenant keys, campaign keys, foreign keys, and per-run uniqueness protect the
relationship data in the same way as the rest of the crawl store.

## Deterministic findings

- **Broken internal link:** emitted only when the target URL was scanned and
  returned no HTTP status or a status of 400 or higher.
- **Exact duplicate content:** emitted only for indexable, non-redirecting,
  successful pages with at least 20 words and the same normalized visible-text
  hash. This is exact-copy evidence, not semantic similarity.
- **Orphan page:** emitted only after an uncapped deep scan successfully loads a
  same-site XML sitemap inventory, for a successful non-redirecting sitemap URL
  other than the seed URL with no recorded incoming internal link. Link-only
  crawl exhaustion is never described as complete orphan coverage.
- **Missing canonical target:** emitted only when the scan follows an internal
  canonical target and confirms that target has no status or an HTTP status of
  400 or higher. An unscanned target is not labeled missing.
- **Redirect chain:** emitted when the fetch required more than one redirect.
- **Invalid structured data:** emitted when at least one JSON-LD block cannot
  be parsed. Unsupported semantic validation is not claimed.

Re-running finalization replaces the run-derived findings instead of creating
duplicates. Partial or capped scans may still confirm broken links and exact
duplicates and broken canonical targets among scanned pages, but they cannot
claim sitemap-backed orphan coverage.

## Customer presentation

Website Health groups findings by issue and shows:

- what is wrong;
- priority and number of affected pages;
- why the issue matters;
- the first practical repair;
- stored URL, HTTP, duplicate, canonical, redirect, or structured-data evidence
  in the expandable technical-details view.

Provider names and internal engine labels are not customer-facing. Evidence is
described as an InsightOS website scan, while Google index evidence retains its
own explicit source and observation time.

## Deferred SEO2 work

SEO2B does not yet add content decay, keyword cannibalization, page-query
mismatch, SERP features, entity/topic comparison, semantic duplicate detection,
HTML microdata/RDFa validation, JavaScript redirect history, or optional Bing
evidence. Those remain independent, testable SEO2 slices.
