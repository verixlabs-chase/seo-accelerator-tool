# Global Learning Graph Overview

## System definition
The Global Learning Graph (GLG) is a cross-campaign knowledge graph that captures reusable relationships between campaign state, strategies, and outcomes.

## Why this component exists
Current learning is strong inside a campaign cycle but weak across campaigns. GLG provides a shared memory layer so evidence from one campaign can improve decisions in others.

## What problem it solves
- Enables cross-campaign transfer learning for strategy selection.
- Improves cold-start intelligence for new campaigns.
- Provides structured context to increase digital twin prediction quality.
- Creates explainable relationship traces for governance and audit.

## Scope
This architecture covers documentation and implementation contracts for the first GLG delivery scope.

## Primary entities
- Nodes: campaign, industry, feature, pattern, strategy, outcome.
- Edges: improves, correlates_with, causes, derived_from.

## Key capabilities
- Cross-campaign retrieval of historically effective strategies.
- Similar-campaign discovery using feature and pattern overlap.
- Industry-conditioned expected strategy performance estimation.
- Pattern and outcome lineage across recommendation cycles.

## Placement in intelligence platform
~~~text
signals
  -> features
  -> pattern detection
  -> recommendation generation
  -> digital twin simulation
  -> execution scheduling
  -> outcome tracking
  -> policy learning
  -> metrics aggregation
  -> GLOBAL LEARNING GRAPH (cross-campaign memory + query)
~~~

## Success criteria
- Query responses include evidence and confidence metadata.
- New campaign onboarding obtains useful priors from day 1.
- Recommendation and digital twin quality improves measurably vs campaign-only baseline.
