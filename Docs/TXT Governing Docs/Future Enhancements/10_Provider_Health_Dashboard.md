# Provider Health Dashboard

## Executive Intent
Expose provider stability, latency, error rates, and quota usage transparently.

## Definitions
Circuit Breaker State: Closed, Open, Half-Open.
Quota Remaining: API usage left in current window.
Error Classification: Retryable vs non-retryable.

## Requirements
- provider_execution_metrics table
- ProviderHealthState model
- Real-time monitoring endpoint

## Required API
GET /api/v1/provider-health/summary