# System Inventory

Date: 2026-03-10

## Documentation Contract

This audit treated the markdown corpus under `docs/`, `backend/docs/`, and `backend/docs/architecture/` as the intended system contract.
No `frontend/docs/` directory exists in the current repository.

## Repository Scale

- Backend application modules: 453 Python files under `backend/app`
- Backend scripts: 10 Python files under `backend/scripts`
- Backend tests: 178 test files under `backend/tests`
- Frontend application files: 10 files under `frontend/app`
- Infrastructure files: 1 file under `infra`
- CI workflows: 3 files under `.github/workflows`
- Markdown documentation files: 195 files under `docs/`, `backend/docs/`, and `frontend/docs/`

## High-Level Platform Map

### Backend Runtime

- Entry point: `backend/app/main.py`
- API routing: `backend/app/api/v1`
- Core config, middleware, security, metrics: `backend/app/core`
- DB session and persistence: `backend/app/db`, `backend/app/models`
- Background tasks: `backend/app/tasks`

### Intelligence Runtime

- Orchestrator: `backend/app/intelligence/intelligence_orchestrator.py`
- Signals and temporal ingestion: `backend/app/intelligence/signal_assembler.py`, `backend/app/intelligence/temporal_ingestion.py`
- Feature engineering: `backend/app/intelligence/feature_store.py`, `backend/app/intelligence/feature_aggregator.py`
- Pattern detection: `backend/app/intelligence/pattern_engine.py`, `backend/app/intelligence/cohort_pattern_engine.py`
- Policy and recommendation generation: `backend/app/intelligence/policy_engine.py`, `backend/app/intelligence/contracts`
- Digital twin: `backend/app/intelligence/digital_twin`
- Execution: `backend/app/intelligence/recommendation_execution_engine.py`
- Outcome tracking: `backend/app/intelligence/outcome_tracker.py`
- Portfolio: `backend/app/intelligence/portfolio`
- Experiments: `backend/app/intelligence/experiments`
- Causal graph: `backend/app/intelligence/causal`
- Causal mechanisms: `backend/app/intelligence/causal_mechanisms`
- Global knowledge graph: `backend/app/intelligence/knowledge_graph`
- Strategy evolution: `backend/app/intelligence/evolution`
- Telemetry and reports: `backend/app/intelligence/telemetry`
- Worker fabric: `backend/app/intelligence/workers`

### Event and Queue Layer

- Event bus: `backend/app/events/event_bus.py`
- Outbox writer: `backend/app/events/emitter.py`
- Event outbox model: `backend/app/events/outbox/event_outbox.py`
- Queue abstraction: `backend/app/events/queue.py`
- Subscriber wiring: `backend/app/events/subscriber_registry.py`

### Services and Domain Modules

- Authentication and onboarding: `backend/app/services/auth_service.py`, `backend/app/services/onboarding_service.py`
- Reporting: `backend/app/services/reporting_service.py`
- Provider infrastructure: `backend/app/providers`, `backend/app/services/provider_*`
- Reference library: `backend/app/reference_library`, `backend/app/services/reference_library_service.py`
- Replay governance: `backend/app/governance/replay`

### Frontend

- App shell and login: `frontend/app/layout.jsx`, `frontend/app/login/page.jsx`
- Dashboard: `frontend/app/dashboard/page.jsx`
- Platform admin views: `frontend/app/platform/**`
- API client helper: `frontend/app/platform/api.js`

### Infrastructure

- Local orchestration: `docker-compose.yml`
- Operational helper: `infra/go-live-preflight.ps1`
- CI workflows: `.github/workflows/ci.yml`, `.github/workflows/backend-ci.yml`, `.github/workflows/preflight-pr.yml`

## Subsystem Classification

| Subsystem | Primary Location |
|---|---|
| API | `backend/app/api/v1` |
| Authentication | `backend/app/api/v1/auth.py`, `backend/app/services/auth_service.py` |
| Campaign lifecycle | `backend/app/services/onboarding_service.py`, `backend/app/api/v1/campaigns.py` |
| Signal ingestion | `backend/app/intelligence/signal_assembler.py`, `backend/app/intelligence/temporal_ingestion.py` |
| Feature engineering | `backend/app/intelligence/feature_store.py`, `backend/app/intelligence/feature_aggregator.py` |
| Pattern detection | `backend/app/intelligence/pattern_engine.py`, `backend/app/intelligence/cohort_pattern_engine.py` |
| Policy engine | `backend/app/intelligence/policy_engine.py` |
| Digital twin | `backend/app/intelligence/digital_twin` |
| Execution engine | `backend/app/intelligence/recommendation_execution_engine.py` |
| Portfolio engine | `backend/app/intelligence/portfolio` |
| Experiment system | `backend/app/intelligence/experiments` |
| Causal learning | `backend/app/intelligence/causal`, `backend/app/intelligence/causal_mechanisms` |
| Strategy evolution | `backend/app/intelligence/evolution` |
| Knowledge graph | `backend/app/intelligence/knowledge_graph` |
| Workers | `backend/app/intelligence/workers`, `backend/app/tasks` |
| Queue | `backend/app/events/queue.py`, Redis/Celery config in `docker-compose.yml` |
| Load protection | `backend/app/core/middleware/rate_limit.py`, `request_size_limit.py` |
| Telemetry | `backend/app/intelligence/telemetry`, `backend/app/core/metrics.py` |
| Reporting | `backend/app/services/reporting_service.py`, `backend/app/api/v1/reports.py` |
| Frontend dashboard | `frontend/app/dashboard/page.jsx`, `frontend/app/platform/page.jsx` |
| API clients | `frontend/app/platform/api.js` |
| Database models | `backend/app/models` |
| Infrastructure | `docker-compose.yml`, `infra/`, `.github/workflows/` |

## Operational Lifecycle Map

Current runtime path is:

1. Tenant and campaign creation through API/services.
2. Signal assembly and temporal persistence in the orchestrator.
3. Feature computation and pattern detection.
4. Policy derivation and recommendation persistence.
5. Digital twin strategy scoring and selection.
6. Execution scheduling and execution.
7. Outcome tracking.
8. Portfolio update and experiment attribution.
9. Experiment completion events into workers.
10. Causal and mechanism learning into the knowledge graph.
11. Strategy evolution and new experiment creation.
12. Learning telemetry snapshots and report persistence.

## Inventory Summary

The repository is a broad full-stack system with a dense backend and a light frontend. The backend contains the real operational complexity: FastAPI routes, SQLAlchemy models, Alembic migrations, Celery-backed workers, event-driven intelligence, and governance/replay layers.
