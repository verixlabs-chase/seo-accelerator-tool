# Causal Strategy Discovery Overview

## Purpose
The Causal Strategy Discovery Engine turns mutation-level execution history into candidate SEO strategies that can be simulated, tested, and promoted safely.

## Architecture Diagram
```text
execution_mutations + recommendation_outcomes + digital_twin_simulations
  -> SEO Flight Recorder
  -> causal outcome analyzer
  -> strategy pattern discovery
  -> strategy hypothesis engine
  -> digital twin validation
  -> strategy evolution experiments
  -> global learning graph + industry intelligence
```

## Data Flow
1. The execution layer persists structured mutations.
2. The flight recorder snapshots before and after outcome metrics.
3. The causal analyzer scores mutation types by support, consistency, variance, and confidence.
4. Pattern discovery identifies repeatable multi-mutation motifs.
5. Hypothesis generation produces stable strategy candidates.
6. Digital twin simulation filters low-confidence ideas before experiments.

## Code Example
```python
summaries = summarize_mutation_causality(db, target_industry_id='hvac')
patterns = discover_strategy_patterns(db)
hypotheses = generate_strategy_hypotheses(patterns)
candidates = plan_experiment_candidates(db, hypotheses=hypotheses, campaign_ids=campaign_ids)
```

## Strategy Discovery Example
`insert_internal_link` rows with `placement=first_paragraph` and three links per page can become `internal_link_cluster_first_paragraph`.

## Experiment Workflow
Discovery -> digital twin screening -> strategy experiment creation -> live execution -> flight recorder feedback.
