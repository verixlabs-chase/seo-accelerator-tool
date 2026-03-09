# Performance Scoring

Each strategy is keyed by the persisted `recommendation_type`.

Inputs:

- win rate from `recommendation_outcomes`
- average delta from observed outcomes
- global learning graph score
- industry prior success rate

Score formula:

- 45% win rate
- 35% normalized average delta
- 10% graph score
- 10% industry prior
