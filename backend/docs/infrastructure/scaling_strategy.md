# Scaling Strategy

This infrastructure phase makes horizontal scale practical, but not complete.

What is now in place:

- durable event ingestion surface
- Celery-based campaign task distribution
- persisted policy learning
- shared model registry state
- execution plugin health checks

What still needs follow-up:

- dedicated stream consumers
- queue autoscaling
- event replay tooling
- plugin fleet rollout controls
- metrics export to external observability backends
