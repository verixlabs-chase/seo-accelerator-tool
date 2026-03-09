# Industry Intelligence Network Overview

## Current scope
The industry intelligence network is implemented as a persisted SQL-backed registry of industry priors.

## What is implemented
- Industry prior schema and query surface in `app/intelligence/industry_models`
- Pattern distribution tracking by industry
- Strategy success-rate tracking by industry
- Average outcome deltas and confidence accumulation
- Runtime updates from pattern, simulation, and outcome events

## How it is used today
- `strategy_transfer_engine.py` reads industry strategy success rates
- transferred strategies carry industry priors into simulation inputs
- predictive strategy ranking can use industry success as a feature

## Current maturity
- State now survives restart and is shared across workers through the primary SQL database
- The system is still a lightweight prior store, not a full standalone modeling service

## Not implemented
- Dedicated training jobs per industry
- Hierarchical prior sharing across adjacent industries
- Large-scale feature embeddings or causal industry models
