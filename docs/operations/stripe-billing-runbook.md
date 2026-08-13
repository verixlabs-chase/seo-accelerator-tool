# Stripe billing runbook

This runbook activates the COM1 subscription lifecycle after the code is
deployed. InsightOS keeps its own organization plan as the authorization record;
Stripe is the payment record and can change access only through a verified
webhook.

## Required server settings

Configure these only on the backend deployment. Do not prefix them with
`NEXT_PUBLIC_` and do not place them in frontend configuration.

- `STRIPE_SECRET_KEY`: restricted test or live secret key.
- `STRIPE_WEBHOOK_SECRET`: signing secret for the exact InsightOS webhook.
- `STRIPE_PRICE_SOLO`: recurring Price ID for Solo.
- `STRIPE_PRICE_GROWTH`: recurring Price ID for Growth.
- `CUSTOMER_APP_BASE_URL`: canonical customer origin, such as
  `https://insightos.verixlabs.com`.

Do not put dollar values in the application environment. Product prices and
currency are configured in Stripe; the application maps the immutable Price ID
to the approved internal plan.

## Stripe setup

1. Create recurring monthly Products/Prices for Solo and Growth in test mode.
2. Configure the customer portal to let customers update payment methods,
   review invoices, and cancel. Enable plan changes only after the intended
   proration and downgrade timing have been tested.
3. Create an HTTPS webhook endpoint at
   `https://<backend-host>/api/v1/billing/webhook`.
4. Subscribe at minimum to:
   - `checkout.session.completed`
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `invoice.paid`
   - `invoice.payment_failed`
   - `invoice.payment_action_required`
5. Copy that endpoint's signing secret into `STRIPE_WEBHOOK_SECRET` and redeploy.

## Test-mode release evidence

Use an organization-owner account and complete these checks before enabling
live mode:

1. Upgrade Solo to Growth through Settings and confirm the browser uses hosted
   checkout.
2. Confirm the plan changes only after a signed active-subscription event.
3. Resend the same event and confirm it is marked duplicate without a second
   plan change.
4. Deliver a payment-failure test event. Confirm Growth access and saved work
   remain while Settings shows the payment-recovery action.
5. Update the payment method in the portal and confirm the recovery warning
   clears after payment succeeds.
6. Cancel at period end and verify the cancellation date is visible. When the
   subscription is actually deleted, confirm new Growth-only work is stopped,
   the organization returns to Solo, and saved work remains available.
7. Review `billing.state.updated` audit entries and the
   `billing_webhook_events` receipt ledger. The ledger must not contain raw
   payloads, card data, customer email, or secret keys.

## Failure handling

- A missing or invalid signature returns a client error and changes no state.
- A temporary processing error returns a server error so Stripe can retry.
- Duplicate completed events return success without applying state twice.
- Older events are recorded as ignored and cannot overwrite newer billing
  state.
- An unknown Price ID fails closed; it never grants the closest plan.
- Enterprise subscriptions are not self-serve in this slice and remain a
  custom-contract workflow.
