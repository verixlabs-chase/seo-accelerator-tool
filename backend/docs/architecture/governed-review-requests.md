# Governed Review Requests

Status: G1.6D2A implemented locally on 2026-08-10. Live transactional delivery
is intentionally unavailable until G1.6D2B.

## Purpose

InsightOS can help a service business ask recent customers for honest Google
reviews without steering only happy customers toward the public review page.
The request record belongs to one organization, one location campaign, and one
physical business location. Portfolio reporting may summarize locations but
does not merge their request records.

## Non-negotiable rules

- Every confirmed eligible customer is treated the same way.
- The recipient model contains no rating, satisfaction, or positive-experience
  field. The saved audience rule explicitly forbids those filters.
- The service rejects wording that conditionally asks only happy customers or
  asks for a positive or five-star review.
- Service completion and a confirmed consent basis are required before a
  customer can enter an email audience.
- An opt-out creates an organization-wide suppression keyed by a one-way
  contact hash. The suppression applies to later campaigns too.
- Raw customer email addresses are masked in API responses.
- A request uses the connected location's Google review URL when available.
  An owner-supplied fallback must be a secure Google or `g.page` URL.
- Campaign results report the difference between the saved starting review
  count and the current saved count. This is a time-window observation only;
  it does not claim that the campaign caused a review.

## Current customer workflow

The Reviews page supports three passive sharing modes:

1. Copyable review link.
2. Downloadable, high-resolution PNG QR code generated in the customer's
   browser from the saved review link.
3. Checkout or kiosk link.

Each mode saves the request wording, immutable policy versions, audience rule,
review link source, starting review count, and lifecycle timestamps. The page
shows which channels are ready and explains unavailable channels in ordinary
language.

The QR mode generates the image locally in the customer's browser. The review
URL is not sent to a separate QR service, and the image is not presented as a
durable platform artifact. The owner is told to test the downloaded code with
a phone before printing it.

## Delivery boundary

The existing email adapter is synthetic and cannot prove a real send. It is
therefore never used to activate a customer review-request campaign. Email
readiness remains false until a real transactional provider and verified sender
are configured.

Live email delivery must add all of the following before release:

- a versioned provider price card;
- credit reservation before dispatch and reconciliation from the receipt;
- an idempotent durable delivery job;
- the exact provider message identifier;
- signed delivered, bounced, complained, and unsubscribed webhooks;
- suppression updates before another send;
- pause, cancel, retry, and audit controls;
- a production proof from consent through final provider outcome.

SMS is a separate product and compliance decision. It remains unavailable
until it has its own provider, written consent rules, price card, allowance,
signed receipts, opt-out handling, and launch approval. Email readiness does
not imply SMS readiness.

## Data model

- `reputation_review_request_campaigns`: location scope, channel, message,
  audience and policy versions, review URL, baseline, and lifecycle.
- `reputation_review_request_recipients`: consent, service completion,
  masked-response contact, eligibility, and suppression state.
- `reputation_review_request_suppressions`: durable organization-wide contact
  suppression by channel.
- `reputation_review_request_deliveries`: reserved durable home for idempotent
  jobs, provider receipts, delivery state, and cost references.

All four tables have tenant and organization indexes, foreign keys, check
constraints, PostgreSQL grants, and row-level security policies.

## API surface

- `GET /api/v1/reviews/request-readiness`
- `GET /api/v1/reviews/request-campaigns?campaign_id=...`
- `POST /api/v1/reviews/request-campaigns`
- `POST /api/v1/reviews/request-campaigns/{id}/recipients`
- `POST /api/v1/reviews/request-campaigns/{id}/control`
- `POST /api/v1/reviews/request-recipients/{id}/suppress`

Only tenant administrators can use these routes. Every campaign and recipient
lookup rechecks tenant and organization scope on the server.
