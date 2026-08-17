import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const settings = readFileSync(
  fileURLToPath(new URL("../app/(product)/settings/page.tsx", import.meta.url)),
  "utf8",
);

test("checkout retries reuse one non-secret client request id", () => {
  assert.match(settings, /BILLING_CHECKOUT_ATTEMPT_KEY/);
  assert.match(settings, /safeSessionStorageGet\(BILLING_CHECKOUT_ATTEMPT_KEY\)/);
  assert.match(settings, /safeSessionStorageSet\(BILLING_CHECKOUT_ATTEMPT_KEY/);
  assert.match(settings, /safeSessionStorageRemove\(BILLING_CHECKOUT_ATTEMPT_KEY\)/);
  assert.match(settings, /function safeSessionStorageGet[\s\S]{0,200}catch \{[\s\S]{0,80}return null/);
  assert.match(settings, /function safeSessionStorageSet[\s\S]{0,200}catch \{/);
  assert.match(settings, /function safeSessionStorageRemove[\s\S]{0,200}catch \{/);
  assert.match(settings, /saved\?\.planCode === planCode/);
  assert.match(settings, /clientRequestId: crypto\.randomUUID\(\)/);
  assert.match(settings, /BILLING_CHECKOUT_ATTEMPT_MAX_AGE_MS/);
  assert.match(settings, /typeof parsed\.expiresAt === "string"[\s\S]{0,200}Date\.parse\(parsed\.expiresAt\)/);
  assert.doesNotMatch(settings, /BillingCheckoutAttempt[\s\S]{0,500}(?:password|access_token|secret):/i);
});

test("checkout sends and preserves the backend idempotency contract", () => {
  const checkoutStart = settings.indexOf("async function startCheckout");
  const checkoutEnd = settings.indexOf("function refreshBillingConfirmation", checkoutStart);
  const checkout = settings.slice(checkoutStart, checkoutEnd);

  assert.match(checkout, /try \{\s*const serverAttempt = billingAttemptFromPending/);
  assert.match(checkout, /billingAttemptFromPending\([\s\S]{0,150}billingSummary\?\.pending_checkout/);
  assert.match(checkout, /serverAttempt \|\| checkoutAttemptForPlan/);
  assert.match(checkout, /plan_code: requestedPlanCode/);
  assert.match(checkout, /client_request_id: attempt\.clientRequestId/);
  assert.match(checkout, /response\.requested_plan_code \|\| attempt\.planCode/);
  assert.match(checkout, /response\.client_request_id \|\| attempt\.clientRequestId/);
  assert.match(checkout, /response\.expires_at \|\| attempt\.expiresAt/);
  assert.match(checkout, /checkout_status\?: "created" \| "reused"/);
  assert.match(checkout, /window\.location\.assign\(response\.url\)/);
});

test("a successful return waits for bounded saved plan confirmation", () => {
  assert.match(settings, /BILLING_CONFIRMATION_DELAYS_MS = \[0, 1000, 1500, 2000, 2500, 3000, 3500, 4000\]/);
  assert.match(settings, /index < BILLING_CONFIRMATION_DELAYS_MS\.length/);
  assert.doesNotMatch(settings, /while \(true\)/);
  assert.match(settings, /platformApi\("\/billing\/summary"/);
  assert.match(settings, /confirmedRequestedPlan === expectedPlanCode/);
  assert.match(settings, /nextSummary\.plan_code === confirmedRequestedPlan/);
  assert.match(settings, /confirmation\?\.client_request_id === expectedClientRequestId/);
  assert.match(settings, /confirmation\?\.session_id === expectedSessionId/);
  assert.match(settings, /expectedClientRequestId\s*\? expectedRequestMatches\s*: expectedSessionMatches/);
  assert.match(settings, /confirmation\?\.subscription_active === true[\s\S]{0,200}expectedCheckoutMatches[\s\S]{0,100}activePlanMatches/);
  assert.match(settings, /confirmation\?\.checkout_completed === true/);
  assert.match(settings, /billingReturned === "success"[\s\S]{0,500}confirmBillingReturn/);
  assert.doesNotMatch(settings, /checkout_confirmation[\s\S]{0,250}\b(?:plan_code|billing_status)\?:/);

  const returnedStart = settings.indexOf('if (billingReturned === "success")');
  const returnedEnd = settings.indexOf('} else if (billingReturned === "cancelled")', returnedStart);
  assert.doesNotMatch(
    settings.slice(returnedStart, returnedEnd),
    /setBillingConfirmationState\("confirmed"\)/,
    "the return URL alone must never activate the plan",
  );
});

test("a success return keeps its checkout session before clearing the URL", () => {
  const returnedStart = settings.indexOf('const billingReturned = returnParams.get("billing")');
  const returnedEnd = settings.indexOf('} else if (billingReturned === "cancelled")', returnedStart);
  const returned = settings.slice(returnedStart, returnedEnd);

  assert.match(returned, /returnParams\.get\("session_id"\)/);
  assert.match(returned, /returnedBillingSessionId[\s\S]{0,500}window\.history\.replaceState/);
  assert.match(returned, /confirmBillingReturn\([\s\S]{0,300}returnedBillingSessionId/);
});

test("closing checkout preserves the reusable pending attempt", () => {
  const cancelledStart = settings.indexOf('billingReturned === "cancelled"');
  const cancelledEnd = settings.indexOf('} else if (googleReturned === "connected")', cancelledStart);
  const cancelled = settings.slice(cancelledStart, cancelledEnd);

  assert.match(cancelled, /Your current plan and saved work were not changed/);
  assert.doesNotMatch(cancelled, /clearBillingCheckoutAttempt/);
});

test("server pending checkout repairs blocked, cleared, or expired browser state", () => {
  assert.match(settings, /pending_checkout\?: \{[\s\S]{0,300}expires_at: string \| null;[\s\S]{0,80}active: boolean/);
  assert.match(settings, /function billingAttemptFromPending[\s\S]{0,350}!pending\?\.active/);
  assert.match(settings, /expiresAt: pending\.expires_at/);
  assert.match(settings, /function reconcileBillingCheckoutAttempt[\s\S]{0,350}saveBillingCheckoutAttempt\(serverAttempt\)/);
  assert.match(settings, /setBillingSummary\(billingResponse\);[\s\S]{0,350}reconcileBillingCheckoutAttempt/);
  assert.match(settings, /serverBillingAttempt \|\| localBillingAttempt/);
  assert.match(settings, /serverAttempt \|\| checkoutAttemptForPlan/);
});

test("a fresh inactive server checkout clears expired local recovery state", () => {
  const reconcileStart = settings.indexOf("function reconcileBillingCheckoutAttempt");
  const reconcileEnd = settings.indexOf("function waitForBillingConfirmation", reconcileStart);
  const reconcile = settings.slice(reconcileStart, reconcileEnd);

  assert.match(reconcile, /if \(serverAttempt\) return saveBillingCheckoutAttempt\(serverAttempt\)/);
  assert.match(reconcile, /clearBillingCheckoutAttempt\(organizationId\)/);
  assert.doesNotMatch(reconcile, /checkout_completed|subscription_active/);
});

test("confirmation timeout stops and gives a safe manual recovery", () => {
  assert.match(settings, /setBillingConfirmationState\("timed_out"\)/);
  assert.match(settings, /Plan confirmation is taking longer than expected/);
  assert.match(settings, /You do not need to purchase it again/);
  assert.match(settings, /Check plan status again/);
  assert.match(settings, /onClick=\{refreshBillingConfirmation\}/);
  assert.match(settings, /billingConfirmationRun\.current \+= 1/);
  assert.doesNotMatch(settings, /Stripe/);
});
