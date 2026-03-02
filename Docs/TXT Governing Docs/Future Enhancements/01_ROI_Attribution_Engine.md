# ROI Attribution Engine

## Executive Intent
This module transforms SEO from a visibility tool into a revenue accountability system. It must compute attributable revenue impact per keyword cluster, campaign, and organization using defensible attribution logic. It is not a vanity analytics feature; it is a financial reporting layer.

This engine is separate from the Organic Media Value Engine.

The Organic Media Value Engine answers:
- What is the paid-equivalent replacement cost of the organic traffic represented by current rankings?
- What is the projected paid-equivalent value if rankings improve?

The ROI Attribution Engine answers:
- What revenue is attributable to SEO?
- What conversion lift has been realized or forecast under attribution assumptions?
- What finance-oriented return metrics can be reported?

## Definitions
Attribution Model: A deterministic or probabilistic model assigning conversion credit to SEO touchpoints.
Conversion Event: A measurable business outcome (form submit, booked job, tracked call).
Revenue Signal: Monetized conversion value imported from CRM or analytics.
Lift Modeling: Statistical estimation of incremental revenue impact beyond baseline.
Incremental Revenue: Revenue above expected baseline without SEO change.

## Module Boundary
This module owns future concepts that are intentionally excluded from SCFE v1:
- conversion delta modeling
- revenue delta modeling
- accounting ROI reporting
- CAC and LTV style business metrics
- finance-oriented efficiency metrics that depend on revenue assumptions

## Requirements
- GA4 integration
- CRM integration (optional but recommended)
- Call tracking ingestion
- Revenue mapping table (keyword -> landing page -> conversion value)
- Caching layer for dashboard queries

## Required API
GET /api/v1/roi/summary?campaign_id=...

## Output Metrics
- Revenue per keyword cluster
- Revenue per campaign
- Cost per acquisition (SEO)
- ROI %
