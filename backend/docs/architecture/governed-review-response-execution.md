# Governed Review Response Execution

Status: implemented locally on 2026-08-10; production activation requires an
authorized Google Business Profile connection and one successful live proof.

## Purpose

This boundary publishes a reply only after a customer has approved the exact
wording and separately confirmed that the reply will be public on Google. It is
not a chatbot and it does not enable automatic review replies.

## Non-negotiable invariants

- AI drafting, human wording approval, and public posting are separate actions.
- Every public reply requires the current confirmation text and an affirmative
  customer action.
- One approved draft can create only one response execution and one durable job.
- Before every attempt, the worker rechecks tenant, organization, location,
  connection, review resource, unanswered state, approved-text hash, and
  provider capability.
- A retry can send only the same approved text to the same provider review
  resource. Google `updateReply` is therefore safe after an uncertain timeout.
- Success requires a matching provider receipt. The receipt, approved-text
  hash, provider method, timestamps, and local response observation are saved.
- A denied provider permission revokes the saved capability and blocks further
  posts. Missing, changed, answered, or policy-rejected reviews fail closed.
- Automatic posting remains disabled.

## Capability lifecycle

1. A platform owner records the applicable Google approval/support reference
   for one active owned-profile connection. Its state becomes
   `validation_authorized`.
2. A customer approves wording and explicitly confirms one public reply.
3. The durable worker calls
   `accounts.locations.reviews.updateReply` for that exact owned review.
4. A matching successful receipt promotes the connection capability to
   `verified`.
5. Access denial or an operator revocation moves it to `revoked`; the customer
   can still copy approved wording but cannot publish through InsightOS.

An enabled API or OAuth scope alone is not accepted as proof of provider write
access.

## Customer API

- `GET /api/v1/reviews/posting-status?campaign_id=...`
- `GET /api/v1/reviews/executions?campaign_id=...`
- `POST /api/v1/reviews/drafts/{draft_id}/publish?campaign_id=...`
- `PATCH /api/v1/reviews/executions/{execution_id}` with `pause`, `resume`,
  `cancel`, or `retry`

The publish request must carry the current confirmation version and
`confirm_publish_to_google: true`.

## Platform control API

- `POST /api/v1/platform/orgs/{organization_id}/review-reply-capability`
- `DELETE /api/v1/platform/orgs/{organization_id}/review-reply-capability`

These routes require the platform-owner role and write both event and audit
records. The customer UI cannot self-authorize provider capability.

## Durable execution and recovery

The `reputation.response.publish` job uses the existing Supabase-backed
`platform_jobs` queue. Transient timeouts, rate limits, and provider server
errors retry with the same execution. Customers can pause, resume, or cancel
work that has not started. Non-retryable provider rejection becomes a visible
blocked state; permission denial additionally revokes capability.

## Production release proof

Before enabling the first customer connection:

1. Confirm the production OAuth project and Business Profile API access.
2. Synchronize the owned review from the same account/location mapping.
3. Record the Google approval reference through platform control.
4. Use a real customer-approved, non-sensitive reply and the explicit publish
   confirmation.
5. Verify exact wording, resource name, Google receipt, local response state,
   immutable observation, audit event, and capability promotion.
6. Exercise a safe staging denial/revocation path and confirm future posts fail
   closed.

No production capability should be mass-enabled from configuration alone.
