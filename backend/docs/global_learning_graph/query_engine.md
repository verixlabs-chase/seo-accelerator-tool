# Query Engine

## System definition
Query Engine provides graph retrieval and scoring APIs for cross-campaign intelligence use cases.

## Query patterns
### 1) Find strategies that historically improved rankings
- Inputs: target outcome (ranking), industry, optional cohort filters.
- Traversal: industry -> strategy -> outcome via improves.
- Ranking: confidence, support_count, outcome_strength, recency.

### 2) Find campaigns similar to current campaign
- Inputs: campaign_id, feature signature, pattern signature.
- Traversal: campaign -> feature/pattern with similarity scoring.
- Ranking: overlap score + outcome profile alignment.

### 3) Estimate expected performance of a strategy
- Inputs: candidate strategy, current campaign context.
- Retrieval: strategy-linked outcomes and comparable campaigns.
- Output: expected delta distribution, confidence interval, evidence set.

### 4) Retrieve patterns relevant to campaign industry
- Inputs: campaign_id or industry_id.
- Traversal: campaign -> industry -> pattern (+ feature lineage).
- Output: top patterns ordered by confidence and freshness.

## Query response contract
- result_items
- score_breakdown
- evidence_edges
- freshness_window
- model_version_used

## Scoring considerations
- Confidence-weighted evidence aggregation.
- Cohort-context match weighting.
- Recency weighting (time decay).
- Minimum support thresholds for returned claims.

## Performance targets (design)
- P50 query latency <= 40 ms.
- P95 query latency <= 120 ms.
- Top-K retrieval optimized for recommendation path.
