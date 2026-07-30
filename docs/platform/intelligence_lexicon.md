# Deterministic SEO Intelligence Lexicon

Status: foundation implemented  
Lexicon ID: `verix.seo.intelligence`  
Built-in version: `1.0.0`  
Last standards review: 2026-07-29

## Purpose

The intelligence lexicon is the governed source of truth between collected SEO
facts, deterministic diagnoses, allowed actions, measured outcomes, and any
future AI narrative layer.

It is intentionally not a prompt library. The deterministic engine owns:

- metric definitions and units
- standards and internal heuristic boundaries
- signal freshness and missing-data behavior
- diagnostic IDs and evidence requirements
- allowed action IDs
- risk tiers and approval requirements
- success metrics and observation windows
- evidence provenance and lexicon version

An AI model may explain, summarize, and prioritize only within the context
produced by the deterministic engine. It may not invent a metric, diagnosis,
action, threshold, causal claim, or outcome.

## Canonical Assets

- Built-in lexicon:
  `backend/reference_library/intelligence/seo_intelligence_v1.json`
- Schema and cross-reference validation:
  `backend/app/intelligence/lexicon/schema.py`
- Tenant-active/fallback loader:
  `backend/app/intelligence/lexicon/loader.py`
- Deterministic metric and Core Web Vitals evaluation:
  `backend/app/intelligence/lexicon/evaluator.py`
- AI decision context:
  `backend/app/intelligence/lexicon/ai_context.py`
- Official-standard drift checks:
  `backend/app/intelligence/lexicon/standards.py`

The v1 bundle contains:

- 40+ typed signals across organic, local, reputation, technical, content,
  competitive, and business data
- the current three Core Web Vitals and supporting TTFB
- contextual organic, local, competitive, content, and technical metrics
- 15 migrated diagnostic definitions
- 35+ stable, governed action definitions
- the existing deterministic policy mappings
- primary-source provenance and plain-language terminology

## Core Web Vitals Truth Model

Current Google/Chrome primary documentation defines:

| Metric | Good | Needs improvement | Poor |
| --- | ---: | ---: | ---: |
| Largest Contentful Paint | `<= 2,500 ms` | `> 2,500 and <= 4,000 ms` | `> 4,000 ms` |
| Interaction to Next Paint | `<= 200 ms` | `> 200 and <= 500 ms` | `> 500 ms` |
| Cumulative Layout Shift | `<= 0.10` | `> 0.10 and <= 0.25` | `> 0.25` |

The system evaluates the 75th percentile. All three metrics must be `good` for
the Core Web Vitals set to pass. Missing any required metric produces
`insufficient_data`; it never produces an estimated pass.

TTFB uses `<= 800 ms` as good and `> 1,800 ms` as poor, but remains explicitly
classified as a supporting Web Vital rather than a Core Web Vital.

Sources:

- [Google Search: Core Web Vitals](https://developers.google.com/search/docs/appearance/core-web-vitals)
- [Chrome: Core Web Vitals thresholds](https://web.dev/articles/defining-core-web-vitals-thresholds)
- [Chrome UX Report API](https://developer.chrome.com/docs/crux/api)
- [Chrome UX Report dimensions](https://developer.chrome.com/docs/crux/methodology/dimensions)
- [Google Search: page experience](https://developers.google.com/search/docs/appearance/page-experience)
- [Chrome: TTFB](https://web.dev/articles/optimize-ttfb)

Google states that Core Web Vitals contribute to page experience, but good
scores do not guarantee rankings and there is no single page-experience ranking
signal. Product copy and AI output must preserve this limitation.

## Field Data and Lab Data

Use the CrUX API for real-user field data:

- rolling 28-day aggregation
- URL or origin scope
- overall, phone, tablet, or desktop form factor
- p75 metric values
- provider histogram boundaries

Use PageSpeed Insights/Lighthouse for lab diagnostics:

- identify likely performance causes
- capture Lighthouse version and test environment
- never substitute a single lab run for CrUX field status

Google plans to discontinue CrUX field data in the PageSpeed Insights API and
recommends the CrUX API directly. The provider boundary is therefore:

```text
CrUX field data -> deterministic status
Lighthouse lab data -> likely cause and repair evidence
Lexicon -> allowed diagnosis and action
AI -> bounded plain-language explanation
```

## Standards Currency

The Vercel-compatible durable job runner creates a periodic
`reference_library.cwv_standards_check` job when:

- `INTELLIGENCE_LEXICON_ENABLED=true`
- `CRUX_API_KEY` is configured
- the configured review bucket is due

The check queries the official CrUX API for only LCP, INP, and CLS. It extracts
the provider histogram boundaries and compares them with the active built-in
lexicon. Results are stored in `reference_library_standards_checks`.

Possible states:

- `current`: the observed official boundaries match
- `incomplete`: the official probe did not return every required metric
- `review_required`: at least one official boundary differs

The standards checker never changes or activates a lexicon automatically. A
change requires:

1. official-source review
2. a new lexicon version
3. schema and cross-reference validation
4. deterministic replay comparison
5. explicit activation
6. rollback availability

This design stays current without allowing an upstream API or documentation
change to silently alter customer recommendations.

## Runtime Selection

For each campaign cycle:

1. Load the tenant's active Reference Library version.
2. Read its persisted `intelligence_lexicon` artifact.
3. Validate the artifact.
4. Fall back to the bundled last-known-good lexicon if no active artifact is
   available or the active payload cannot be decoded.
5. Record lexicon ID, version, and schema version with each newly persisted
   recommendation.

The production activation mode remains `recommendation_only`. Lexicon
activation does not enable site mutations, provider checks, or autonomous
policy learning.

## API Surface

All routes are tenant-scoped and role protected.

- `GET /api/v1/reference-library/lexicon`
- `POST /api/v1/reference-library/core-web-vitals/evaluate`
- `GET /api/v1/reference-library/core-web-vitals/standards/status`
- `POST /api/v1/reference-library/core-web-vitals/standards/check`
  (`platform_admin`)
- `POST /api/v1/reference-library/ai-decision-context`

The AI context response contains:

- verified facts
- deterministic assessments
- selected diagnostic definitions
- allowed actions only
- source metadata
- explicit non-negotiable model rules
- a constrained output shape

## Environment

```dotenv
REFERENCE_LIBRARY_LOADER_ENABLED=true
REFERENCE_LIBRARY_ENFORCE_VALIDATION=true
INTELLIGENCE_LEXICON_ENABLED=true
CRUX_API_KEY=
CWV_STANDARDS_PROBE_ORIGIN=https://web.dev
CWV_STANDARDS_REVIEW_INTERVAL_DAYS=30
```

Enable the Chrome UX Report API in Google Cloud and use a restricted API key.
Do not expose the key to the browser.

## Extension Rules

Every new provider or product capability must add or map:

1. typed signals with source and freshness
2. metrics with units, aggregation, scope, and provenance
3. deterministic diagnostics with minimum evidence
4. stable action IDs with risk, effort, owner, and success measurement
5. primary sources or an explicit internal-heuristic label
6. plain-language terminology for service-business owners
7. cross-reference and replay tests

Universal thresholds must not be invented for contextual metrics such as CTR,
rank position, review velocity, or competitor gaps. Their defaults must remain
explicitly labeled as internal heuristics and later calibrated by cohort only
after minimum sample and governance requirements are satisfied.
