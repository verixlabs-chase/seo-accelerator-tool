# Organic Media Value Engine v1

## Purpose
Organic Media Value Engine v1 is the platform's replacement-cost valuation layer.

It estimates what the current or projected organic traffic would cost to buy through paid search using deterministic CTR and CPC assumptions.

## What It Is
Implemented design target:
- deterministic CTR modeling
- estimated clicks by rank
- paid-equivalent value
- rank-improvement forecasting
- keyword simulation
- hash-stamped deterministic outputs

## What It Is Not
This is not accounting ROI.

It does not define:
- attributable revenue
- conversion lift accounting
- CAC
- LTV
- finance-grade ROI reporting

Those concerns belong to the separate ROI Attribution Engine.

## Architectural Boundary
Organic Media Value Engine v1 produces valuation outputs.

Examples:
- current paid-equivalent value
- projected paid-equivalent value
- value delta
- keyword opportunity gap

ROI Attribution Engine consumes separate business and revenue inputs.

Capital allocation is a downstream consumer of Organic Media Value Engine outputs. It uses valuation signals for prioritization, but it does not change the valuation model into an accounting model.

## Schema Compatibility
Current analytics schema does not conflict with this separation.

Current state:
- `campaign_daily_metrics` is a campaign-level analytics fact table
- it may carry nullable `cost` and `revenue` fields for future financial workflows
- it does not currently implement ROI logic
- there is no existing keyword-level valuation table in runtime yet

That means Organic Media Value Engine v1 can be added as a separate keyword-level layer without redefining current analytics storage as ROI accounting.
