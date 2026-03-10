# Execution Layer Architecture

## Current Shape

The execution layer now has two concrete paths:

- Website mutation execution through the WordPress plugin contract.
- Non-website execution paths that still depend on provider-native connectors, such as Google Business Profile updates.

The canonical runtime path is:

1. `recommendation_execution_engine.schedule_execution()` applies governance, risk, and approval policy.
2. The selected executor generates deterministic structured mutations.
3. `recommendation_execution_engine.execute_recommendation()` delivers those mutations through the WordPress transport when the executor produces website mutations.
4. The platform persists each mutation with before and after state snapshots.
5. Rollback replays persisted rollback payloads through the same transport.

## Maturity

This is production-oriented mutation plumbing, not a full multi-CMS execution mesh.

Implemented now:

- Structured mutation payloads for website mutations.
- Persisted mutation audit trail.
- Rollback endpoint and stored snapshots.
- WordPress transport contract with signed requests.
- Deterministic local transport in test mode.

Still partial:

- `optimize_gbp_profile` remains outside website mutation delivery.
- Live mutation delivery depends on configured `wordpress_plugin` credentials.
- The backend defines the plugin contract; the WordPress plugin must implement the documented endpoints.
