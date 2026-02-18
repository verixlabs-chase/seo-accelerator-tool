# Glossary

## Core Engine
Production modules defined in roadmap Phases 1-6 (crawl, rank, content, internal linking, authority, campaign intelligence, reporting).

## Intelligence Layer
Systems that consume Core Engine outputs and produce structured, explainable recommendations.

## Reference Library
Versioned, execution-agnostic, data-only knowledge system containing metric definitions, thresholds, diagnostics, validation rules, and remediation mappings.

## Recommendation Engine
Service that consumes structured data and the Reference Library to produce recommendation action objects.

## Execution Layer
Controlled system that applies approved changes through CMS/Git integrations under risk-tier constraints.

## Risk Tier (0-4)
Operational risk classification:
- 0 = insight only
- 1 = draft only
- 2 = low-risk publish
- 3 = high-risk publish (approval required)
- 4 = structural change (PR required)

## Roadmap Phase
Formal milestone with bounded scope and acceptance criteria.

## Metric
Measurable system value with defined units, percentile model, thresholds, and validation.

## Threshold
Boundary defining Good, Needs Improvement, and Poor states.

## Diagnostic Signal
Secondary metric used to infer likely root cause.

## Recommendation
Structured remediation action tied to diagnostic signals.

## Validation Rule
Measurement confirming recommendation success criteria.
