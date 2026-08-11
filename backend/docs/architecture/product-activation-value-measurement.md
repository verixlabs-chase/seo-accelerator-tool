# Product Activation and Value Measurement

Status: PA1 first slice implemented locally on August 11, 2026.

## Purpose

InsightOS must prove that customers can finish setup, reach a useful result,
follow a recommendation, and return for more value. Operational audit logs are
not reused for this purpose: audit evidence is deduplicated around mutations,
while product measurement needs a separate append-only sequence of explicitly
defined customer events.

This first slice does not connect PostHog or another analytics vendor. It stores
the governed events in the application database and exposes only aggregate
measurement to platform owners. A later exporter must consume this contract;
it may not enable autocapture or session replay.

## Privacy boundary

The browser may send only a registered event name, an internal campaign ID, an
optional idempotency key, and short allowlisted labels. The service rejects
unknown events, unknown fields, unknown values, cross-organization campaigns,
and prohibited sensitive-field names.

Never record:

- access or refresh tokens, authorization headers, passwords, secrets, or API keys;
- emails, phone numbers, page URLs, page content, prompts, model responses, or review text;
- customer search queries, keywords, provider payloads, form contents, or arbitrary free text.

Customer feedback is structured. It contains a 1-5 rating and one governed
reason code; there is no comment box. Feedback remains product research and
does not modify a recommendation, its evidence, or the intelligence engine.

## Event contract

Every event definition in `product_analytics_service.py` includes an owner,
purpose, schema version, retention period, allowed properties, and
instrumentation status. The platform taxonomy endpoint exposes those fields so
missing and partial instrumentation is visible.

The first active journey records:

1. `onboarding.started`
2. `onboarding.completed`
3. `value.first_verified_insight` only after a recommendation includes saved evidence
4. `workspace.location_switched`
5. `recommendation.viewed`
6. `forecast.viewed` only when a supported forecast is available
7. `action.step_completed`
8. `action.outcome_available` after a new measured outcome is saved

The last three evidence-bearing milestones (`value.first_verified_insight`,
`action.step_completed`, and `action.outcome_available`) are emitted only by
the server after the underlying read or write succeeds. The customer event API
rejects attempts to create them directly.

Registered events for connections, recommendation decisions, reports,
notifications, help, support escalation, and automation remain marked planned
until their owning product surfaces are deliberately instrumented.

## Aggregate metrics

`GET /api/v1/platform/product-value/summary` is restricted to platform owners
and platform admins. It returns no organization, user, campaign, or subject
identifiers. It measures:

- completed setup and activation rate;
- first evidence-backed value and time from setup start to first value;
- organizations that complete at least one checklist step;
- repeated value, defined as useful product activity in two or more calendar weeks;
- organizations that reached first value but have no useful activity in the last 14 days;
- aggregate funnels by saved plan type;
- recommendation-usefulness and forecast-trust response counts and ratings;
- registered, active, silent, and planned instrumentation;
- the number of synthetic events excluded from all customer metrics.

Synthetic/demo activity must set `is_synthetic=true` through trusted server or
fixture code. Internal-anchor and platform-sponsored organizations are marked
synthetic automatically and excluded from both the funnel denominator and
feedback totals. The public event and feedback endpoints never accept that
field.

## API and authorization

- `POST /api/v1/product-analytics/events`: authenticated organization member,
  organization context required.
- `POST /api/v1/product-analytics/feedback`: authenticated organization member,
  structured fields only.
- `GET /api/v1/platform/product-value/summary`: platform owner/admin only.
- `GET /api/v1/platform/product-value/taxonomy`: platform owner/admin only.

PostgreSQL row-level security requires matching tenant and organization
context, except for an authenticated platform context. The application role has
only select/insert privileges on these append-only tables.

## Next PA1 slices

- Instrument connection success/failure, recommendation decisions, report use,
  help, support escalation, and governed automation results at their server-side
  completion boundaries.
- Add explicit roadmap-experiment definitions with success metrics and stop
  conditions.
- Validate retention deletion jobs before any external analytics export.
- If an external service is approved, add a redacting exporter behind the
  governed registry and keep autocapture and session replay disabled.
