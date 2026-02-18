# Reference Library CWV Build Checklist

## Current Implemented Slice
- Reference Library persistence model and migration (`reference_library_versions`, `reference_library_artifacts`, `reference_library_validation_runs`, `reference_library_activations`).
- Loader service that ingests CWV metrics and performance recommendations from:
  - `Docs/TXT Governing Docs/Future Enhancements/reference_library/metrics/core_web_vitals.json`
  - `Docs/TXT Governing Docs/Future Enhancements/reference_library/recommendations/perf_recommendations.json`
- Validation rules enforcing:
  - metric schema integrity
  - threshold fields presence (`good`, `needs_improvement`, `units`)
  - recommendation key linkage integrity
- API endpoints:
  - `POST /api/v1/reference-library/validate`
  - `POST /api/v1/reference-library/activate`
  - `GET /api/v1/reference-library/versions`
  - `GET /api/v1/reference-library/active`
- Celery task scaffolding:
  - `reference_library.validate_artifact`
  - `reference_library.activate_version`
  - `reference_library.reload_cache`
- `reference_library.rollback_version`
- Platform admin role enforcement for Reference Library routes.
- CI/runtime schema validation using typed artifact models for CWV metrics and recommendation catalog.

## Remaining Work Before True Product Testing
- Add schema-versioned artifact validator contracts (JSON schema files and version registry in CI).
- Add activation safety checks:
  - block activation when latest validation failed
  - require explicit approval metadata for Tier 2+ rollout
- Wire Recommendation Engine reads to active Reference Library version (no hardcoded thresholds).
- Add runtime cache layer with invalidation strategy for loader hot-reload.
- Add audit assertions in tests for validate/activate/rollback actions.
- Add feature-flag-off tests for loader endpoints.
- Add integration tests proving CWV recommendation generation includes:
  - `confidence_score`
  - `evidence[]`
  - `risk_tier`
  - rollback plan field.
- Add staging smoke test pipeline for:
  - validate -> activate -> query active -> rollback.
