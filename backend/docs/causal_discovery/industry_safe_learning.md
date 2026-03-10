# Industry Safe Learning

## Layered Evidence Model
```text
score = campaign_evidence * 0.6 + industry_evidence * 0.3 + global_evidence * 0.1
```

## Safety Guardrails
- Campaign evidence dominates promotion decisions.
- Industry similarity gates prevent unsafe transfer.
- Global evidence only nudges exploration, not direct promotion.
- Low-similarity industries cannot share causal strategy promotion signals.

## Code Example
```python
allowed = similarity_allows_transfer(db, 'hvac', 'legal')
```

## Strategy Discovery Example
A local service linking pattern can transfer from HVAC to plumbing, but not automatically into ecommerce.

## Experiment Workflow
Cross-industry ideas require similarity approval before digital twin validation or experiments.
