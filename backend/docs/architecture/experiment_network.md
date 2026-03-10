# Experiment Network

Audit prerequisite: Future system audits must read the architecture documents in `backend/docs/architecture/` before performing code analysis.

## Purpose
The experiment network deterministically assigns campaigns into control or treatment for exploratory policies and attributes later outcomes back to the experiment.

## Runtime pipeline
```text
portfolio explore allocation
  -> ensure_experiment_for_policy()
  -> assign_campaign_to_experiment()
  -> treatment keeps experimental policy
  -> control retains baseline

record_outcome()
  -> record_experiment_outcome()
     -> find assignment by campaign + assigned_policy_id
     -> persist ExperimentOutcome
     -> analyze_experiment_for_outcome()
     -> publish experiment.completed after commit
```

## Core modules
- `app/intelligence/experiments/experiment_registry.py`
- `app/intelligence/experiments/experiment_assignment.py`
- `app/intelligence/experiments/experiment_engine.py`
- `app/intelligence/experiments/experiment_analysis.py`

## Data models
- `Experiment`
- `ExperimentAssignment`
- `ExperimentOutcome`
- runtime `ExperimentResult`, `ExperimentAssignmentResult`

## Event integrations
- `record_outcome()` publishes `experiment.completed` after the DB commit succeeds
- the causal learning processor subscribes to `experiment.completed`

## Safety constraints
- campaign assignment is deterministic from hash bucket
- duplicate outcome attribution is blocked by unique `outcome_id`
- experiment completion events are delayed until after commit

## Scaling risks
- assignment lookup is on the synchronous outcome path
- active experiment count grows with number of explore policies and evolved strategies
- current experiment model is policy-centric and does not yet represent richer feature cohorts
