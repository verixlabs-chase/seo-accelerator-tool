# Strategy Transfer Engine

## Objective
Transfer proven strategies from similar campaigns to new or sparse-history campaigns.

## Transfer flow
~~~text
Campaign Context -> Graph Query -> Top Strategy Set
                -> Digital Twin Validation -> Risk Gate
                -> Deployable Strategy Plan
~~~

## Retrieval inputs
- Industry and cohort context.
- Active feature and pattern signatures.
- Campaign constraints (budget, risk tier, execution limits).

## Transfer scoring
- Graph evidence confidence.
- Historical outcome strength.
- Cohort match quality.
- Simulation-adjusted expected value.

## Safety checks
- Reject transfers with weak support or stale evidence.
- Require simulation confidence threshold for autonomous execution.
- Fall back to campaign-local baseline if transfer confidence collapses.
