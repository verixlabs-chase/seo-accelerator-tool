from __future__ import annotations

import hashlib
import hmac
import json
import time

from app.core.config import get_settings
from app.models.audit_log import AuditLog
from app.models.billing import BillingWebhookEvent
from app.models.organization import Organization
from app.services import stripe_billing_service


def _login(client, email: str, password: str) -> tuple[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    data = response.json()["data"]
    return data["access_token"], data["user"]["tenant_id"]


def _signature(raw_body: bytes, secret: str, timestamp: int) -> str:
    digest = hmac.new(
        secret.encode(), f"{timestamp}.".encode() + raw_body, hashlib.sha256
    ).hexdigest()
    return f"t={timestamp},v1={digest}"


def _configure_stripe(monkeypatch) -> None:
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_billing")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_billing")
    monkeypatch.setenv("STRIPE_PRICE_SOLO", "price_solo")
    monkeypatch.setenv("STRIPE_PRICE_GROWTH", "price_growth")
    monkeypatch.setenv("CUSTOMER_APP_BASE_URL", "https://insightos.example")
    get_settings.cache_clear()


def _clear_stripe(monkeypatch) -> None:
    for key in (
        "STRIPE_SECRET_KEY",
        "STRIPE_WEBHOOK_SECRET",
        "STRIPE_PRICE_SOLO",
        "STRIPE_PRICE_GROWTH",
        "CUSTOMER_APP_BASE_URL",
    ):
        monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()


def test_owner_can_open_growth_checkout_without_exposing_secret(
    client, db_session, monkeypatch
) -> None:
    _configure_stripe(monkeypatch)
    captured: dict = {}

    def fake_post(path, fields, *, idempotency_key):
        captured.update(path=path, fields=dict(fields), key=idempotency_key)
        return {
            "id": "cs_test_123",
            "url": "https://checkout.stripe.test/session",
            "expires_at": int(time.time()) + 1800,
        }

    monkeypatch.setattr(stripe_billing_service, "_stripe_post", fake_post)
    try:
        token, organization_id = _login(client, "org-owner@example.com", "pass-org-owner")
        organization = db_session.get(Organization, organization_id)
        organization.plan_type = "standard"
        organization.stripe_customer_id = None
        organization.stripe_subscription_id = None
        organization.billing_status = None
        db_session.commit()

        response = client.post(
            "/api/v1/billing/checkout",
            headers={"Authorization": f"Bearer {token}"},
            json={"plan_code": "multi_location"},
        )

        assert response.status_code == 200
        assert response.json()["data"]["url"] == "https://checkout.stripe.test/session"
        assert captured["path"] == "/checkout/sessions"
        assert captured["fields"]["mode"] == "subscription"
        assert captured["fields"]["line_items[0][price]"] == "price_growth"
        assert captured["fields"]["metadata[organization_id]"] == organization_id
        assert captured["fields"]["success_url"].startswith("https://insightos.example/settings")
        assert "sk_test_billing" not in str(response.json())
        assert (
            db_session.query(AuditLog)
            .filter(
                AuditLog.tenant_id == organization_id,
                AuditLog.event_type == "billing.checkout.created",
            )
            .count()
            == 1
        )
    finally:
        _clear_stripe(monkeypatch)


def test_non_owner_cannot_start_checkout(client, monkeypatch) -> None:
    _configure_stripe(monkeypatch)
    try:
        token, _organization_id = _login(client, "org-admin@example.com", "pass-org-admin")
        response = client.post(
            "/api/v1/billing/checkout",
            headers={"Authorization": f"Bearer {token}"},
            json={"plan_code": "multi_location"},
        )
        assert response.status_code == 403
    finally:
        _clear_stripe(monkeypatch)


def test_signed_subscription_webhook_changes_internal_plan_once(
    client, db_session, monkeypatch
) -> None:
    _configure_stripe(monkeypatch)
    try:
        _token, organization_id = _login(client, "org-owner@example.com", "pass-org-owner")
        organization = db_session.get(Organization, organization_id)
        organization.plan_type = "standard"
        organization.stripe_customer_id = None
        organization.stripe_subscription_id = None
        organization.billing_status = None
        organization.billing_last_event_created_at = None
        db_session.commit()
        timestamp = int(time.time())
        event = {
            "id": "evt_subscription_active",
            "type": "customer.subscription.updated",
            "created": timestamp,
            "api_version": "2026-07-29",
            "data": {
                "object": {
                    "id": "sub_growth",
                    "object": "subscription",
                    "customer": "cus_growth",
                    "status": "active",
                    "cancel_at_period_end": False,
                    "current_period_end": timestamp + 2_592_000,
                    "metadata": {
                        "organization_id": organization_id,
                        "plan_code": "multi_location",
                    },
                    "items": {"data": [{"price": {"id": "price_growth"}}]},
                }
            },
        }
        raw = json.dumps(event, separators=(",", ":")).encode()
        headers = {"Stripe-Signature": _signature(raw, "whsec_billing", timestamp)}

        first = client.post("/api/v1/billing/webhook", content=raw, headers=headers)
        second = client.post("/api/v1/billing/webhook", content=raw, headers=headers)

        assert first.status_code == 200
        assert first.json()["data"] == {
            "received": True,
            "duplicate": False,
            "status": "processed",
        }
        assert second.status_code == 200
        assert second.json()["data"]["duplicate"] is True
        db_session.expire_all()
        organization = db_session.get(Organization, organization_id)
        assert organization.plan_type == "multi_location"
        assert organization.billing_status == "active"
        assert organization.stripe_customer_id == "cus_growth"
        assert organization.stripe_subscription_id == "sub_growth"
        assert (
            db_session.query(BillingWebhookEvent)
            .filter(BillingWebhookEvent.provider_event_id == event["id"])
            .count()
            == 1
        )
    finally:
        _clear_stripe(monkeypatch)


def test_payment_failure_preserves_plan_and_cancellation_returns_to_solo(
    client, db_session, monkeypatch
) -> None:
    _configure_stripe(monkeypatch)
    try:
        _token, organization_id = _login(client, "org-owner@example.com", "pass-org-owner")
        organization = db_session.get(Organization, organization_id)
        organization.plan_type = "multi_location"
        organization.stripe_customer_id = "cus_recovery"
        organization.stripe_subscription_id = "sub_recovery"
        organization.billing_status = "active"
        organization.billing_last_event_created_at = None
        db_session.commit()
        timestamp = int(time.time())

        failed = {
            "id": "evt_invoice_failed",
            "type": "invoice.payment_failed",
            "created": timestamp,
            "data": {
                "object": {
                    "id": "in_failed",
                    "object": "invoice",
                    "customer": "cus_recovery",
                    "subscription": "sub_recovery",
                }
            },
        }
        failed_raw = json.dumps(failed, separators=(",", ":")).encode()
        failed_response = client.post(
            "/api/v1/billing/webhook",
            content=failed_raw,
            headers={"Stripe-Signature": _signature(failed_raw, "whsec_billing", timestamp)},
        )
        assert failed_response.status_code == 200
        db_session.expire_all()
        organization = db_session.get(Organization, organization_id)
        assert organization.plan_type == "multi_location"
        assert organization.billing_status == "past_due"

        canceled = {
            "id": "evt_subscription_canceled",
            "type": "customer.subscription.deleted",
            "created": timestamp + 1,
            "data": {
                "object": {
                    "id": "sub_recovery",
                    "object": "subscription",
                    "customer": "cus_recovery",
                    "status": "canceled",
                    "cancel_at_period_end": False,
                    "metadata": {"organization_id": organization_id},
                    "items": {"data": [{"price": {"id": "price_growth"}}]},
                }
            },
        }
        canceled_raw = json.dumps(canceled, separators=(",", ":")).encode()
        canceled_response = client.post(
            "/api/v1/billing/webhook",
            content=canceled_raw,
            headers={
                "Stripe-Signature": _signature(
                    canceled_raw, "whsec_billing", timestamp + 1
                )
            },
        )
        assert canceled_response.status_code == 200
        db_session.expire_all()
        organization = db_session.get(Organization, organization_id)
        assert organization.plan_type == "solo"
        assert organization.billing_status == "canceled"
    finally:
        _clear_stripe(monkeypatch)


def test_invalid_or_stale_webhook_signature_is_rejected(monkeypatch) -> None:
    _configure_stripe(monkeypatch)
    try:
        raw = b'{}'
        timestamp = int(time.time())
        try:
            stripe_billing_service.verify_webhook_signature(
                raw, f"t={timestamp},v1=bad", now_timestamp=timestamp
            )
            raise AssertionError("invalid signature was accepted")
        except stripe_billing_service.BillingError as exc:
            assert exc.reason_code == "invalid_billing_webhook_signature"

        stale_timestamp = timestamp - 301
        try:
            stripe_billing_service.verify_webhook_signature(
                raw,
                _signature(raw, "whsec_billing", stale_timestamp),
                now_timestamp=timestamp,
            )
            raise AssertionError("stale signature was accepted")
        except stripe_billing_service.BillingError as exc:
            assert exc.reason_code == "stale_billing_webhook"
    finally:
        _clear_stripe(monkeypatch)


def test_unknown_subscription_price_fails_closed_without_partial_state(
    client, db_session, monkeypatch
) -> None:
    _configure_stripe(monkeypatch)
    try:
        _token, organization_id = _login(client, "org-owner@example.com", "pass-org-owner")
        organization = db_session.get(Organization, organization_id)
        organization.plan_type = "standard"
        organization.stripe_customer_id = None
        organization.stripe_subscription_id = None
        organization.billing_status = None
        organization.billing_last_event_created_at = None
        db_session.commit()
        timestamp = int(time.time())
        event = {
            "id": "evt_unknown_price",
            "type": "customer.subscription.updated",
            "created": timestamp,
            "data": {
                "object": {
                    "id": "sub_unknown",
                    "object": "subscription",
                    "customer": "cus_unknown",
                    "status": "active",
                    "metadata": {"organization_id": organization_id},
                    "items": {"data": [{"price": {"id": "price_not_approved"}}]},
                }
            },
        }
        raw = json.dumps(event, separators=(",", ":")).encode()
        response = client.post(
            "/api/v1/billing/webhook",
            content=raw,
            headers={"Stripe-Signature": _signature(raw, "whsec_billing", timestamp)},
        )

        assert response.status_code == 400
        db_session.expire_all()
        organization = db_session.get(Organization, organization_id)
        assert organization.plan_type == "standard"
        assert organization.stripe_customer_id is None
        assert organization.stripe_subscription_id is None
        assert organization.billing_status is None
        receipt = (
            db_session.query(BillingWebhookEvent)
            .filter(BillingWebhookEvent.provider_event_id == event["id"])
            .one()
        )
        assert receipt.status == "failed"
        assert receipt.error_code == "billing_price_not_supported"
    finally:
        _clear_stripe(monkeypatch)
