from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import get_settings
from app.models.audit_log import AuditLog
from app.models.billing import BillingWebhookEvent
from app.models.business_location import BusinessLocation
from app.models.campaign import Campaign
from app.models.entitlement import Entitlement
from app.models.organization import Organization
from app.domain.entitlement_codes import LIMIT_ACTIVE_LOCATIONS
from app.services import commercial_plan_service, stripe_billing_service


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


def _post_event(client, event: dict, timestamp: int):
    raw = json.dumps(event, separators=(",", ":")).encode()
    return client.post(
        "/api/v1/billing/webhook",
        content=raw,
        headers={"Stripe-Signature": _signature(raw, "whsec_billing", timestamp)},
    )


def _seed_pending_checkout(
    organization: Organization,
    *,
    request_id: str,
    session_id: str,
    plan_code: str = "multi_location",
) -> None:
    organization.billing_pending_checkout_request_id = request_id
    organization.billing_pending_checkout_session_id = session_id
    organization.billing_pending_checkout_plan_code = plan_code
    organization.billing_pending_checkout_expires_at = datetime.now(UTC) + timedelta(
        minutes=30
    )


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
            json={
                "plan_code": "multi_location",
                "client_request_id": "0f741b56-5617-4b94-9a50-10320dfed017",
            },
        )

        assert response.status_code == 200
        assert response.json()["data"]["url"] == "https://checkout.stripe.test/session"
        assert captured["path"] == "/checkout/sessions"
        assert captured["fields"]["mode"] == "subscription"
        assert captured["fields"]["line_items[0][price]"] == "price_growth"
        assert captured["fields"]["metadata[organization_id]"] == organization_id
        assert (
            captured["fields"]["metadata[client_request_id]"]
            == "0f741b56-5617-4b94-9a50-10320dfed017"
        )
        assert (
            captured["fields"]["subscription_data[metadata][client_request_id]"]
            == "0f741b56-5617-4b94-9a50-10320dfed017"
        )
        assert captured["fields"]["success_url"].startswith("https://insightos.example/settings")
        assert captured["key"].startswith("insightos-checkout-")
        assert response.json()["data"]["client_request_id"] == (
            "0f741b56-5617-4b94-9a50-10320dfed017"
        )
        assert response.json()["data"]["requested_plan_code"] == "multi_location"
        assert response.json()["data"]["checkout_status"] == "created"
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
            json={
                "plan_code": "multi_location",
                "client_request_id": "b2cf5ec0-c370-416e-bbb0-e8fb195ab7f8",
            },
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


def test_failed_webhook_receipt_retry_is_claimed_once_and_attempt_count_is_truthful(
    client, db_session, monkeypatch
) -> None:
    _configure_stripe(monkeypatch)
    try:
        _token, organization_id = _login(client, "org-owner@example.com", "pass-org-owner")
        organization = db_session.get(Organization, organization_id)
        organization.plan_type = "solo"
        organization.stripe_customer_id = None
        organization.stripe_subscription_id = None
        organization.billing_status = None
        organization.billing_subscription_status = None
        db_session.commit()
        timestamp = int(time.time())
        event = {
            "id": "evt_failed_receipt_retry",
            "type": "customer.subscription.updated",
            "created": timestamp,
            "data": {
                "object": {
                    "id": "sub_failed_receipt_retry",
                    "object": "subscription",
                    "customer": "cus_failed_receipt_retry",
                    "status": "active",
                    "metadata": {"organization_id": organization_id},
                    "items": {"data": [{"price": {"id": "price_retry_after_failure"}}]},
                }
            },
        }

        failed = _post_event(client, event, timestamp)

        assert failed.status_code == 400
        receipt = (
            db_session.query(BillingWebhookEvent)
            .filter(BillingWebhookEvent.provider_event_id == event["id"])
            .one()
        )
        assert receipt.status == "failed"
        assert receipt.attempt_count == 1

        monkeypatch.setenv("STRIPE_PRICE_GROWTH", "price_retry_after_failure")
        get_settings.cache_clear()
        retry = _post_event(client, event, timestamp)
        duplicate = _post_event(client, event, timestamp)

        assert retry.status_code == 200
        assert retry.json()["data"] == {
            "received": True,
            "duplicate": False,
            "status": "processed",
        }
        assert duplicate.status_code == 200
        assert duplicate.json()["data"] == {
            "received": True,
            "duplicate": True,
            "status": "processed",
        }
        db_session.expire_all()
        receipt = (
            db_session.query(BillingWebhookEvent)
            .filter(BillingWebhookEvent.provider_event_id == event["id"])
            .one()
        )
        organization = db_session.get(Organization, organization_id)
        assert receipt.status == "processed"
        assert receipt.attempt_count == 2
        assert receipt.error_code is None
        assert organization.plan_type == "multi_location"
        assert organization.billing_status == "active"
        assert (
            db_session.query(AuditLog)
            .filter(
                AuditLog.tenant_id == organization_id,
                AuditLog.event_type == "billing.state.updated",
            )
            .count()
            == 1
        )
    finally:
        _clear_stripe(monkeypatch)


def test_checkout_request_id_is_stable_and_invalid_values_never_call_provider(
    client, db_session, monkeypatch
) -> None:
    _configure_stripe(monkeypatch)
    calls: list[str] = []

    def fake_post(path, fields, *, idempotency_key):
        assert path == "/checkout/sessions"
        calls.append(idempotency_key)
        return {
            "id": "cs_stable_request",
            "url": "https://checkout.stripe.test/stable",
            "expires_at": int(time.time()) + 1800,
        }

    monkeypatch.setattr(stripe_billing_service, "_stripe_post", fake_post)
    try:
        token, organization_id = _login(client, "org-owner@example.com", "pass-org-owner")
        organization = db_session.get(Organization, organization_id)
        organization.plan_type = "solo"
        organization.stripe_customer_id = None
        organization.stripe_subscription_id = None
        organization.billing_status = None
        db_session.commit()
        body = {
            "plan_code": "growth",
            "client_request_id": "347703f7-c74c-43a7-915c-57b6b6dac1e6",
        }

        first = client.post(
            "/api/v1/billing/checkout",
            headers={"Authorization": f"Bearer {token}"},
            json=body,
        )
        second = client.post(
            "/api/v1/billing/checkout",
            headers={"Authorization": f"Bearer {token}"},
            json=body,
        )
        invalid = client.post(
            "/api/v1/billing/checkout",
            headers={"Authorization": f"Bearer {token}"},
            json={"plan_code": "growth", "client_request_id": "../../unsafe"},
        )

        assert first.status_code == 200
        assert second.status_code == 200
        assert invalid.status_code == 422
        assert len(calls) == 2
        assert calls[0] == calls[1]
        assert "347703f7" not in calls[0]
        assert first.json()["data"]["requested_plan_code"] == "multi_location"
    finally:
        _clear_stripe(monkeypatch)


def test_readiness_and_portal_are_safe_saved_state_only(
    client, db_session, monkeypatch
) -> None:
    _configure_stripe(monkeypatch)
    portal_fields: dict[str, str] = {}

    def fake_post(path, fields, *, idempotency_key):
        assert path == "/billing_portal/sessions"
        assert idempotency_key.startswith("portal-")
        portal_fields.update(dict(fields))
        return {"url": "https://billing.stripe.test/portal"}

    monkeypatch.setattr(stripe_billing_service, "_stripe_post", fake_post)
    try:
        token, organization_id = _login(client, "org-owner@example.com", "pass-org-owner")
        organization = db_session.get(Organization, organization_id)
        organization.plan_type = "multi_location"
        organization.stripe_customer_id = "cus_portal"
        organization.stripe_subscription_id = "sub_portal"
        organization.billing_status = "active"
        db_session.commit()

        readiness = client.get(
            "/api/v1/billing/readiness",
            headers={"Authorization": f"Bearer {token}"},
        )
        portal = client.post(
            "/api/v1/billing/portal",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert readiness.status_code == 200
        assert readiness.json()["data"] == {
            "source": "saved_configuration",
            "network_checked": False,
            "billing_mode": "subscription",
            "provider_configured": True,
            "webhook_configured": True,
            "checkout_configured": True,
            "portal_configured": True,
            "configured_plan_codes": ["solo", "multi_location"],
        }
        assert "cus_portal" not in readiness.text
        assert "sk_test_billing" not in readiness.text
        assert portal.status_code == 200
        assert portal.json()["data"]["url"] == "https://billing.stripe.test/portal"
        assert portal_fields["customer"] == "cus_portal"
    finally:
        _clear_stripe(monkeypatch)


def test_full_growth_cancellation_and_solo_lifecycle_preserves_saved_data_and_gates(
    client, db_session, monkeypatch
) -> None:
    _configure_stripe(monkeypatch)
    try:
        token, organization_id = _login(client, "org-owner@example.com", "pass-org-owner")
        organization = db_session.get(Organization, organization_id)
        organization.plan_type = "solo"
        organization.stripe_customer_id = None
        organization.stripe_subscription_id = None
        organization.billing_status = None
        organization.billing_last_event_created_at = None
        timestamp = int(time.time())
        request_id = "5e77ccb5-bd82-4611-b5e1-e8898596123c"
        _seed_pending_checkout(
            organization,
            request_id=request_id,
            session_id="cs_growth_closeout",
        )
        db_session.commit()
        saved_campaign_ids = {
            item.id
            for item in db_session.query(Campaign)
            .filter(Campaign.organization_id == organization_id)
            .all()
        }
        checkout = {
            "id": "evt_checkout_completed_closeout",
            "type": "checkout.session.completed",
            "created": timestamp,
            "data": {
                "object": {
                    "id": "cs_growth_closeout",
                    "object": "checkout.session",
                    "customer": "cus_growth_closeout",
                    "subscription": "sub_growth_closeout",
                    "client_reference_id": organization_id,
                    "metadata": {
                        "organization_id": organization_id,
                        "requested_plan_code": "multi_location",
                        "client_request_id": request_id,
                    },
                }
            },
        }
        assert _post_event(client, checkout, timestamp).status_code == 200
        db_session.expire_all()
        organization = db_session.get(Organization, organization_id)
        assert organization.plan_type == "solo"
        assert organization.billing_status == "checkout_completed"
        summary = client.get(
            "/api/v1/billing/summary",
            headers={"Authorization": f"Bearer {token}"},
        ).json()["data"]
        assert summary["checkout_confirmation"] == {
            "client_request_id": request_id,
            "session_id": "cs_growth_closeout",
            "requested_plan_code": "multi_location",
            "checkout_completed": True,
            "subscription_active": False,
        }

        active_with_scheduled_cancellation = {
            "id": "evt_growth_active_scheduled_cancel",
            "type": "customer.subscription.updated",
            "created": timestamp + 1,
            "data": {
                "object": {
                    "id": "sub_growth_closeout",
                    "object": "subscription",
                    "customer": "cus_growth_closeout",
                    "status": "active",
                    "cancel_at_period_end": True,
                    "current_period_end": timestamp + 2_592_000,
                    "metadata": {
                        "organization_id": organization_id,
                        "plan_code": "multi_location",
                        "client_request_id": request_id,
                    },
                    "items": {"data": [{"price": {"id": "price_growth"}}]},
                }
            },
        }
        assert _post_event(
            client, active_with_scheduled_cancellation, timestamp + 1
        ).status_code == 200
        db_session.expire_all()
        organization = db_session.get(Organization, organization_id)
        assert organization.plan_type == "multi_location"
        assert organization.billing_status == "active"
        assert organization.billing_cancel_at_period_end is True
        assert commercial_plan_service.require_commercial_feature(
            db_session,
            organization_id=organization_id,
            feature_code=commercial_plan_service.FEATURE_WORDPRESS_EXECUTION,
        )["available"] is True
        active_summary = client.get(
            "/api/v1/billing/summary",
            headers={"Authorization": f"Bearer {token}"},
        ).json()["data"]
        assert active_summary["plan_code"] == "multi_location"
        assert active_summary["checkout_confirmation"]["subscription_active"] is True

        downgraded = {
            "id": "evt_growth_downgraded_to_solo",
            "type": "customer.subscription.updated",
            "created": timestamp + 2,
            "data": {
                "object": {
                    "id": "sub_growth_closeout",
                    "object": "subscription",
                    "customer": "cus_growth_closeout",
                    "status": "active",
                    "cancel_at_period_end": False,
                    "current_period_end": timestamp + 2_592_000,
                    # Checkout metadata can remain unchanged after a portal price change.
                    "metadata": {
                        "organization_id": organization_id,
                        "plan_code": "multi_location",
                        "client_request_id": request_id,
                    },
                    "items": {"data": [{"price": {"id": "price_solo"}}]},
                }
            },
        }
        assert _post_event(client, downgraded, timestamp + 2).status_code == 200
        db_session.expire_all()
        organization = db_session.get(Organization, organization_id)
        assert organization.plan_type == "solo"
        assert organization.billing_status == "active"
        with pytest.raises(commercial_plan_service.CommercialPlanFeatureDenied):
            commercial_plan_service.require_commercial_feature(
                db_session,
                organization_id=organization_id,
                feature_code=commercial_plan_service.FEATURE_WORDPRESS_EXECUTION,
            )

        deleted = {
            "id": "evt_growth_final_deletion",
            "type": "customer.subscription.deleted",
            "created": timestamp + 3,
            "data": {
                "object": {
                    "id": "sub_growth_closeout",
                    "object": "subscription",
                    "customer": "cus_growth_closeout",
                    "status": "active",
                    "cancel_at_period_end": False,
                    "metadata": {"organization_id": organization_id},
                    "items": {"data": [{"price": {"id": "price_solo"}}]},
                }
            },
        }
        assert _post_event(client, deleted, timestamp + 3).status_code == 200

        late_invoice = {
            "id": "evt_invoice_after_final_deletion",
            "type": "invoice.paid",
            "created": timestamp + 4,
            "data": {
                "object": {
                    "id": "in_after_deletion",
                    "object": "invoice",
                    "customer": "cus_growth_closeout",
                    "subscription": "sub_growth_closeout",
                }
            },
        }
        assert _post_event(client, late_invoice, timestamp + 4).status_code == 200
        db_session.expire_all()
        organization = db_session.get(Organization, organization_id)
        assert organization.plan_type == "solo"
        assert organization.billing_status == "canceled"
        assert organization.billing_cancel_at_period_end is False
        with pytest.raises(commercial_plan_service.CommercialPlanFeatureDenied):
            commercial_plan_service.require_commercial_feature(
                db_session,
                organization_id=organization_id,
                feature_code=commercial_plan_service.FEATURE_WORDPRESS_EXECUTION,
            )
        assert {
            item.id
            for item in db_session.query(Campaign)
            .filter(Campaign.organization_id == organization_id)
            .all()
        } == saved_campaign_ids
    finally:
        _clear_stripe(monkeypatch)


def test_reused_webhook_event_id_with_different_payload_fails_closed(
    client, db_session, monkeypatch
) -> None:
    _configure_stripe(monkeypatch)
    try:
        timestamp = int(time.time())
        first = {
            "id": "evt_reused_payload",
            "type": "customer.created",
            "created": timestamp,
            "data": {"object": {"id": "cus_first", "object": "customer"}},
        }
        conflicting = {
            "id": "evt_reused_payload",
            "type": "customer.created",
            "created": timestamp,
            "data": {"object": {"id": "cus_different", "object": "customer"}},
        }

        first_response = _post_event(client, first, timestamp)
        conflicting_response = _post_event(client, conflicting, timestamp)

        assert first_response.status_code == 200
        assert first_response.json()["data"] == {
            "received": True,
            "duplicate": False,
            "status": "ignored",
        }
        assert conflicting_response.status_code == 409
        assert (
            conflicting_response.json()["errors"][0]["details"]["reason_code"]
            == "billing_event_payload_conflict"
        )
        receipt = (
            db_session.query(BillingWebhookEvent)
            .filter(BillingWebhookEvent.provider_event_id == "evt_reused_payload")
            .one()
        )
        assert receipt.status == "ignored"
        assert receipt.error_code == "unsupported_billing_event_type"
        assert receipt.attempt_count == 1
    finally:
        _clear_stripe(monkeypatch)


def test_pending_checkout_is_durable_reusable_and_expires_before_replacement(
    client, db_session, monkeypatch
) -> None:
    _configure_stripe(monkeypatch)
    calls: list[dict[str, str]] = []
    sessions: dict[str, str] = {}

    def fake_post(path, fields, *, idempotency_key):
        assert path == "/checkout/sessions"
        values = dict(fields)
        request_id = values["metadata[client_request_id]"]
        session_id = sessions.setdefault(request_id, f"cs_{len(sessions) + 1}")
        calls.append({"request_id": request_id, "key": idempotency_key})
        return {
            "id": session_id,
            "url": f"https://checkout.stripe.test/{session_id}",
            "expires_at": int(time.time()) + 1800,
        }

    monkeypatch.setattr(stripe_billing_service, "_stripe_post", fake_post)
    try:
        token, organization_id = _login(client, "org-owner@example.com", "pass-org-owner")
        organization = db_session.get(Organization, organization_id)
        organization.plan_type = "solo"
        organization.stripe_customer_id = None
        organization.stripe_subscription_id = None
        organization.billing_status = None
        stripe_billing_service._clear_pending_checkout(organization)
        db_session.commit()
        headers = {"Authorization": f"Bearer {token}"}
        first_request = "26cb821c-cbe5-43af-bf43-44e2d34d6fa0"
        other_request = "7e31bdf1-ffca-425e-b86c-e6b313f2b7cf"

        first = client.post(
            "/api/v1/billing/checkout",
            headers=headers,
            json={"plan_code": "growth", "client_request_id": first_request},
        )
        blocked = client.post(
            "/api/v1/billing/checkout",
            headers=headers,
            json={"plan_code": "growth", "client_request_id": other_request},
        )
        reopened = client.post(
            "/api/v1/billing/checkout",
            headers=headers,
            json={"plan_code": "growth", "client_request_id": first_request},
        )

        assert first.status_code == 200
        assert first.json()["data"]["checkout_status"] == "created"
        assert blocked.status_code == 409
        assert (
            blocked.json()["errors"][0]["details"]["reason_code"]
            == "checkout_already_pending"
        )
        assert reopened.status_code == 200
        assert reopened.json()["data"]["checkout_status"] == "reused"
        assert reopened.json()["data"]["session_id"] == first.json()["data"]["session_id"]
        assert len(calls) == 2
        assert calls[0]["key"] == calls[1]["key"]

        summary = client.get("/api/v1/billing/summary", headers=headers).json()["data"]
        assert summary["pending_checkout"]["active"] is True
        assert summary["pending_checkout"]["client_request_id"] == first_request
        assert summary["checkout_confirmation"]["checkout_completed"] is False
        assert summary["checkout_confirmation"]["subscription_active"] is False

        db_session.expire_all()
        organization = db_session.get(Organization, organization_id)
        organization.billing_pending_checkout_expires_at = datetime.now(UTC) - timedelta(
            seconds=1
        )
        db_session.commit()
        replacement = client.post(
            "/api/v1/billing/checkout",
            headers=headers,
            json={"plan_code": "growth", "client_request_id": other_request},
        )

        assert replacement.status_code == 200
        assert replacement.json()["data"]["checkout_status"] == "created"
        assert replacement.json()["data"]["session_id"] != first.json()["data"]["session_id"]
        db_session.expire_all()
        organization = db_session.get(Organization, organization_id)
        assert organization.billing_pending_checkout_request_id == other_request
        assert organization.billing_pending_checkout_session_id == replacement.json()["data"][
            "session_id"
        ]
    finally:
        _clear_stripe(monkeypatch)


@pytest.mark.parametrize("checkout_first", [True, False])
def test_terminal_subscription_can_rotate_only_through_correlated_checkout_in_any_order(
    client, db_session, monkeypatch, checkout_first
) -> None:
    _configure_stripe(monkeypatch)
    try:
        _token, organization_id = _login(client, "org-owner@example.com", "pass-org-owner")
        organization = db_session.get(Organization, organization_id)
        organization.plan_type = "solo"
        organization.stripe_customer_id = "cus_rotation"
        organization.stripe_subscription_id = "sub_terminal_old"
        organization.billing_status = "canceled"
        organization.billing_subscription_status = "canceled"
        organization.billing_subscription_event_type = "customer.subscription.deleted"
        organization.billing_subscription_event_created_at = datetime.now(UTC) - timedelta(
            days=1
        )
        request_id = (
            "f51e8aab-ed2f-4bc1-86f7-18c1476e68a9"
            if checkout_first
            else "1a6beb43-036b-4dca-92c9-a5ef469cead9"
        )
        session_id = "cs_rotate_checkout_first" if checkout_first else "cs_rotate_sub_first"
        _seed_pending_checkout(
            organization,
            request_id=request_id,
            session_id=session_id,
        )
        db_session.commit()
        timestamp = int(time.time())
        checkout = {
            "id": f"evt_rotate_checkout_{checkout_first}",
            "type": "checkout.session.completed",
            "created": timestamp,
            "data": {
                "object": {
                    "id": session_id,
                    "object": "checkout.session",
                    "customer": "cus_rotation",
                    "subscription": "sub_replacement_new",
                    "client_reference_id": organization_id,
                    "metadata": {
                        "organization_id": organization_id,
                        "requested_plan_code": "multi_location",
                        "client_request_id": request_id,
                    },
                }
            },
        }
        subscription = {
            "id": f"evt_rotate_subscription_{checkout_first}",
            "type": "customer.subscription.created",
            "created": timestamp + 1,
            "data": {
                "object": {
                    "id": "sub_replacement_new",
                    "object": "subscription",
                    "customer": "cus_rotation",
                    "status": "active",
                    "cancel_at_period_end": False,
                    "metadata": {
                        "organization_id": organization_id,
                        "plan_code": "multi_location",
                        "client_request_id": request_id,
                    },
                    "items": {"data": [{"price": {"id": "price_growth"}}]},
                }
            },
        }
        ordered_events = [checkout, subscription] if checkout_first else [subscription, checkout]

        for offset, event in enumerate(ordered_events):
            event_timestamp = timestamp + offset
            event["created"] = event_timestamp
            assert _post_event(client, event, event_timestamp).status_code == 200

        db_session.expire_all()
        organization = db_session.get(Organization, organization_id)
        assert organization.stripe_subscription_id == "sub_replacement_new"
        assert organization.plan_type == "multi_location"
        assert organization.billing_subscription_status == "active"
        assert organization.billing_status == "active"
        assert organization.billing_pending_checkout_request_id is None
        assert organization.billing_last_checkout_request_id == request_id
        assert organization.billing_last_checkout_session_id == session_id
        assert (
            db_session.query(AuditLog)
            .filter(
                AuditLog.tenant_id == organization_id,
                AuditLog.event_type == "billing.subscription.rotated",
            )
            .count()
            == 1
        )
    finally:
        _clear_stripe(monkeypatch)


@pytest.mark.parametrize("deleted_first", [True, False])
def test_equal_second_terminal_subscription_event_always_wins(
    client, db_session, monkeypatch, deleted_first
) -> None:
    _configure_stripe(monkeypatch)
    try:
        _token, organization_id = _login(client, "org-owner@example.com", "pass-org-owner")
        organization = db_session.get(Organization, organization_id)
        organization.plan_type = "multi_location"
        organization.stripe_customer_id = "cus_equal_second"
        organization.stripe_subscription_id = "sub_equal_second"
        organization.billing_status = "active"
        organization.billing_subscription_status = "active"
        organization.billing_subscription_event_type = "customer.subscription.created"
        organization.billing_subscription_event_created_at = datetime.now(UTC) - timedelta(
            seconds=1
        )
        db_session.commit()
        timestamp = int(time.time())

        active = {
            "id": f"evt_equal_active_{deleted_first}",
            "type": "customer.subscription.updated",
            "created": timestamp,
            "data": {
                "object": {
                    "id": "sub_equal_second",
                    "object": "subscription",
                    "customer": "cus_equal_second",
                    "status": "active",
                    "metadata": {"organization_id": organization_id},
                    "items": {"data": [{"price": {"id": "price_growth"}}]},
                }
            },
        }
        deleted = {
            "id": f"evt_equal_deleted_{deleted_first}",
            "type": "customer.subscription.deleted",
            "created": timestamp,
            "data": {
                "object": {
                    "id": "sub_equal_second",
                    "object": "subscription",
                    "customer": "cus_equal_second",
                    "status": "canceled",
                    "metadata": {"organization_id": organization_id},
                    "items": {"data": [{"price": {"id": "price_growth"}}]},
                }
            },
        }
        ordered_events = [deleted, active] if deleted_first else [active, deleted]

        for event in ordered_events:
            assert _post_event(client, event, timestamp).status_code == 200

        db_session.expire_all()
        organization = db_session.get(Organization, organization_id)
        assert organization.plan_type == "solo"
        assert organization.billing_subscription_status == "canceled"
        assert organization.billing_subscription_event_type == "customer.subscription.deleted"
        assert organization.billing_status == "canceled"
    finally:
        _clear_stripe(monkeypatch)


def test_signed_cancellation_updates_suspended_closure_org_without_reviving_or_deleting_data(
    client, db_session, monkeypatch
) -> None:
    _configure_stripe(monkeypatch)
    try:
        _token, organization_id = _login(client, "org-owner@example.com", "pass-org-owner")
        organization = db_session.get(Organization, organization_id)
        commercial_plan_service.apply_commercial_plan(
            db_session,
            organization_id=organization_id,
            plan_code="multi_location",
        )
        organization.status = "closure_pending"
        organization.stripe_customer_id = "cus_closure_pending"
        organization.stripe_subscription_id = "sub_closure_pending"
        organization.billing_status = "active"
        organization.billing_subscription_status = "active"
        organization.billing_subscription_event_type = "customer.subscription.created"
        organization.billing_subscription_event_created_at = datetime.now(UTC) - timedelta(
            minutes=1
        )
        locations = [
            BusinessLocation(
                organization_id=organization_id,
                name=f"Saved closure location {index}",
                status="active",
            )
            for index in range(2)
        ]
        db_session.add_all(locations)
        db_session.commit()
        timestamp = int(time.time())
        deleted = {
            "id": "evt_closure_pending_subscription_deleted",
            "type": "customer.subscription.deleted",
            "created": timestamp,
            "data": {
                "object": {
                    "id": "sub_closure_pending",
                    "object": "subscription",
                    "customer": "cus_closure_pending",
                    "status": "canceled",
                    "metadata": {"organization_id": organization_id},
                    "items": {"data": [{"price": {"id": "price_growth"}}]},
                }
            },
        }

        response = _post_event(client, deleted, timestamp)

        assert response.status_code == 200
        db_session.expire_all()
        organization = db_session.get(Organization, organization_id)
        assert organization.status == "closure_pending"
        assert organization.billing_status == "canceled"
        assert organization.billing_subscription_status == "canceled"
        assert organization.plan_type == "solo"
        allowance = (
            db_session.query(Entitlement)
            .filter(
                Entitlement.organization_id == organization_id,
                Entitlement.code == LIMIT_ACTIVE_LOCATIONS,
            )
            .one()
        )
        assert allowance.limit_value == 1
        assert (
            db_session.query(BusinessLocation)
            .filter(BusinessLocation.id.in_([row.id for row in locations]))
            .count()
            == 2
        )
        assert {
            row.status
            for row in db_session.query(BusinessLocation)
            .filter(BusinessLocation.id.in_([row.id for row in locations]))
            .all()
        } == {"active"}
        receipt = (
            db_session.query(BillingWebhookEvent)
            .filter(
                BillingWebhookEvent.provider_event_id
                == "evt_closure_pending_subscription_deleted"
            )
            .one()
        )
        assert receipt.status == "processed"
    finally:
        _clear_stripe(monkeypatch)


def test_payment_and_subscription_streams_are_ordered_independently(
    client, db_session, monkeypatch
) -> None:
    _configure_stripe(monkeypatch)
    try:
        _token, organization_id = _login(client, "org-owner@example.com", "pass-org-owner")
        organization = db_session.get(Organization, organization_id)
        organization.plan_type = "multi_location"
        organization.stripe_customer_id = "cus_cross_stream"
        organization.stripe_subscription_id = "sub_cross_stream"
        organization.billing_status = "active"
        organization.billing_subscription_status = "active"
        organization.billing_subscription_event_type = "customer.subscription.created"
        organization.billing_subscription_event_created_at = datetime.now(UTC) - timedelta(
            minutes=5
        )
        organization.billing_payment_status = None
        organization.billing_payment_event_created_at = None
        organization.billing_payment_event_type = None
        db_session.commit()
        timestamp = int(time.time())

        failed = {
            "id": "evt_cross_invoice_failed",
            "type": "invoice.payment_failed",
            "created": timestamp + 2,
            "data": {
                "object": {
                    "id": "in_cross_failed",
                    "object": "invoice",
                    "customer": "cus_cross_stream",
                    "subscription": "sub_cross_stream",
                }
            },
        }
        older_paid = {
            "id": "evt_cross_invoice_older_paid",
            "type": "invoice.paid",
            "created": timestamp + 1,
            "data": {
                "object": {
                    "id": "in_cross_older_paid",
                    "object": "invoice",
                    "customer": "cus_cross_stream",
                    "subscription": "sub_cross_stream",
                }
            },
        }
        active_update = {
            "id": "evt_cross_subscription_active",
            "type": "customer.subscription.updated",
            "created": timestamp + 3,
            "data": {
                "object": {
                    "id": "sub_cross_stream",
                    "object": "subscription",
                    "customer": "cus_cross_stream",
                    "status": "active",
                    "metadata": {"organization_id": organization_id},
                    "items": {"data": [{"price": {"id": "price_growth"}}]},
                }
            },
        }
        deleted = {
            "id": "evt_cross_subscription_deleted",
            "type": "customer.subscription.deleted",
            "created": timestamp + 4,
            "data": {
                "object": {
                    "id": "sub_cross_stream",
                    "object": "subscription",
                    "customer": "cus_cross_stream",
                    "status": "canceled",
                    "metadata": {"organization_id": organization_id},
                    "items": {"data": [{"price": {"id": "price_growth"}}]},
                }
            },
        }
        newest_paid = {
            "id": "evt_cross_invoice_newest_paid",
            "type": "invoice.paid",
            "created": timestamp + 5,
            "data": {
                "object": {
                    "id": "in_cross_newest_paid",
                    "object": "invoice",
                    "customer": "cus_cross_stream",
                    "subscription": "sub_cross_stream",
                }
            },
        }

        assert _post_event(client, failed, timestamp + 2).status_code == 200
        assert _post_event(client, older_paid, timestamp + 1).status_code == 200
        assert _post_event(client, active_update, timestamp + 3).status_code == 200
        db_session.expire_all()
        organization = db_session.get(Organization, organization_id)
        assert organization.billing_payment_status == "past_due"
        assert organization.billing_payment_event_type == "invoice.payment_failed"
        assert organization.billing_subscription_status == "active"
        assert organization.billing_status == "past_due"

        assert _post_event(client, deleted, timestamp + 4).status_code == 200
        assert _post_event(client, newest_paid, timestamp + 5).status_code == 200
        db_session.expire_all()
        organization = db_session.get(Organization, organization_id)
        assert organization.billing_payment_status == "paid"
        assert organization.billing_payment_event_type == "invoice.paid"
        assert organization.billing_subscription_status == "canceled"
        assert organization.billing_status == "canceled"
        assert organization.plan_type == "solo"
    finally:
        _clear_stripe(monkeypatch)


def test_created_subscription_rejects_signed_plan_that_disagrees_with_price(
    client, db_session, monkeypatch
) -> None:
    _configure_stripe(monkeypatch)
    try:
        _token, organization_id = _login(client, "org-owner@example.com", "pass-org-owner")
        organization = db_session.get(Organization, organization_id)
        organization.plan_type = "solo"
        organization.stripe_customer_id = None
        organization.stripe_subscription_id = None
        organization.billing_status = None
        organization.billing_subscription_status = None
        db_session.commit()
        timestamp = int(time.time())
        event = {
            "id": "evt_created_plan_price_mismatch",
            "type": "customer.subscription.created",
            "created": timestamp,
            "data": {
                "object": {
                    "id": "sub_created_plan_price_mismatch",
                    "object": "subscription",
                    "customer": "cus_created_plan_price_mismatch",
                    "status": "active",
                    "metadata": {
                        "organization_id": organization_id,
                        "plan_code": "solo",
                    },
                    "items": {"data": [{"price": {"id": "price_growth"}}]},
                }
            },
        }

        response = _post_event(client, event, timestamp)

        assert response.status_code == 400
        assert (
            response.json()["errors"][0]["details"]["reason_code"]
            == "billing_plan_price_mismatch"
        )
        db_session.expire_all()
        organization = db_session.get(Organization, organization_id)
        assert organization.plan_type == "solo"
        assert organization.stripe_customer_id is None
        assert organization.stripe_subscription_id is None
        assert organization.billing_subscription_status is None
        receipt = (
            db_session.query(BillingWebhookEvent)
            .filter(
                BillingWebhookEvent.provider_event_id
                == "evt_created_plan_price_mismatch"
            )
            .one()
        )
        assert receipt.status == "failed"
    finally:
        _clear_stripe(monkeypatch)


def test_legacy_recovery_subscription_returns_to_active_after_newer_paid_invoice(
    client, db_session, monkeypatch
) -> None:
    _configure_stripe(monkeypatch)
    try:
        _token, organization_id = _login(client, "org-owner@example.com", "pass-org-owner")
        organization = db_session.get(Organization, organization_id)
        event_time = datetime.now(UTC) - timedelta(minutes=10)
        organization.plan_type = "multi_location"
        organization.stripe_customer_id = "cus_legacy_recovery"
        organization.stripe_subscription_id = "sub_legacy_recovery"
        organization.billing_status = "past_due"
        organization.billing_subscription_status = "active"
        organization.billing_subscription_event_created_at = event_time
        organization.billing_subscription_event_type = "legacy.recovery_inferred"
        organization.billing_payment_status = "past_due"
        organization.billing_payment_event_created_at = event_time
        organization.billing_payment_event_type = "legacy.migrated"
        db_session.commit()
        timestamp = int(time.time())
        event = {
            "id": "evt_legacy_recovery_paid",
            "type": "invoice.paid",
            "created": timestamp,
            "data": {
                "object": {
                    "id": "in_legacy_recovery_paid",
                    "object": "invoice",
                    "customer": "cus_legacy_recovery",
                    "subscription": "sub_legacy_recovery",
                }
            },
        }

        response = _post_event(client, event, timestamp)

        assert response.status_code == 200
        db_session.expire_all()
        organization = db_session.get(Organization, organization_id)
        assert organization.plan_type == "multi_location"
        assert organization.billing_subscription_status == "active"
        assert organization.billing_subscription_event_type == "legacy.recovery_inferred"
        assert organization.billing_payment_status == "paid"
        assert organization.billing_payment_event_type == "invoice.paid"
        assert organization.billing_status == "active"
    finally:
        _clear_stripe(monkeypatch)


@pytest.mark.parametrize(
    ("invoice_subscription_id", "invoice_parent", "expected_reason"),
    [
        (
            None,
            {"type": "quote_details", "quote_details": {"quote": "qt_one_off_invoice"}},
            "billing_invoice_subscription_missing",
        ),
        ("sub_unrelated_invoice", None, "billing_invoice_subscription_mismatch"),
        (
            "sub_current_invoice_guard",
            {"type": "quote_details", "quote_details": {"quote": "qt_with_legacy"}},
            "billing_invoice_subscription_conflict",
        ),
        (
            "sub_current_invoice_guard",
            {"type": "subscription_details", "subscription_details": {}},
            "billing_invoice_subscription_missing",
        ),
    ],
)
def test_invoice_without_current_subscription_never_changes_payment_health(
    client,
    db_session,
    monkeypatch,
    invoice_subscription_id,
    invoice_parent,
    expected_reason,
) -> None:
    _configure_stripe(monkeypatch)
    try:
        _token, organization_id = _login(client, "org-owner@example.com", "pass-org-owner")
        organization = db_session.get(Organization, organization_id)
        organization.plan_type = "multi_location"
        organization.stripe_customer_id = "cus_invoice_guard"
        organization.stripe_subscription_id = "sub_current_invoice_guard"
        organization.billing_status = "past_due"
        organization.billing_subscription_status = "active"
        organization.billing_payment_status = "past_due"
        organization.billing_payment_event_type = "invoice.payment_failed"
        organization.billing_payment_event_created_at = datetime.now(UTC) - timedelta(
            minutes=1
        )
        db_session.commit()
        timestamp = int(time.time())
        invoice_object = {
            "id": f"in_guard_{invoice_subscription_id or 'one_off'}",
            "object": "invoice",
            "customer": "cus_invoice_guard",
        }
        if invoice_subscription_id is not None:
            invoice_object["subscription"] = invoice_subscription_id
        if invoice_parent is not None:
            invoice_object["parent"] = invoice_parent
        event = {
            "id": f"evt_invoice_guard_{invoice_subscription_id or 'one_off'}",
            "type": "invoice.paid",
            "created": timestamp,
            "data": {"object": invoice_object},
        }

        response = _post_event(client, event, timestamp)

        assert response.status_code == 400
        assert response.json()["errors"][0]["details"]["reason_code"] == expected_reason
        db_session.expire_all()
        organization = db_session.get(Organization, organization_id)
        assert organization.billing_payment_status == "past_due"
        assert organization.billing_payment_event_type == "invoice.payment_failed"
        assert organization.billing_status == "past_due"
        receipt = (
            db_session.query(BillingWebhookEvent)
            .filter(BillingWebhookEvent.provider_event_id == event["id"])
            .one()
        )
        assert receipt.organization_id == organization_id
        assert receipt.status == "failed"
        assert receipt.error_code == expected_reason
    finally:
        _clear_stripe(monkeypatch)


@pytest.mark.parametrize("expanded_subscription", [False, True])
def test_current_stripe_invoice_parent_subscription_updates_payment_health(
    client, db_session, monkeypatch, expanded_subscription
) -> None:
    _configure_stripe(monkeypatch)
    try:
        _token, organization_id = _login(client, "org-owner@example.com", "pass-org-owner")
        organization = db_session.get(Organization, organization_id)
        organization.plan_type = "multi_location"
        organization.stripe_customer_id = "cus_current_invoice_shape"
        organization.stripe_subscription_id = "sub_current_invoice_shape"
        organization.billing_status = "past_due"
        organization.billing_subscription_status = "active"
        organization.billing_payment_status = "past_due"
        organization.billing_payment_event_type = "invoice.payment_failed"
        organization.billing_payment_event_created_at = datetime.now(UTC) - timedelta(
            minutes=1
        )
        db_session.commit()
        timestamp = int(time.time())
        subscription_value = (
            {"id": "sub_current_invoice_shape"}
            if expanded_subscription
            else "sub_current_invoice_shape"
        )
        event = {
            "id": f"evt_current_invoice_parent_shape_{expanded_subscription}",
            "type": "invoice.paid",
            "created": timestamp,
            "data": {
                "object": {
                    "id": "in_current_invoice_parent_shape",
                    "object": "invoice",
                    "customer": "cus_current_invoice_shape",
                    "parent": {
                        "type": "subscription_details",
                        "subscription_details": {
                            "subscription": subscription_value
                        },
                    },
                }
            },
        }

        response = _post_event(client, event, timestamp)

        assert response.status_code == 200
        assert response.json()["data"]["status"] == "processed"
        db_session.expire_all()
        organization = db_session.get(Organization, organization_id)
        assert organization.billing_payment_status == "paid"
        assert organization.billing_status == "active"
    finally:
        _clear_stripe(monkeypatch)


def test_current_stripe_subscription_item_period_uses_earliest_valid_end(
    client, db_session, monkeypatch
) -> None:
    _configure_stripe(monkeypatch)
    try:
        _token, organization_id = _login(client, "org-owner@example.com", "pass-org-owner")
        organization = db_session.get(Organization, organization_id)
        organization.plan_type = "multi_location"
        organization.stripe_customer_id = "cus_current_period_shape"
        organization.stripe_subscription_id = "sub_current_period_shape"
        organization.stripe_price_id = "price_growth"
        organization.billing_status = "active"
        organization.billing_subscription_status = "active"
        organization.billing_subscription_event_type = "customer.subscription.updated"
        organization.billing_subscription_event_created_at = datetime.now(UTC) - timedelta(
            seconds=2
        )
        db_session.commit()
        timestamp = int(time.time())
        earliest_period_end = timestamp + 1_800
        later_period_end = timestamp + 3_600
        event = {
            "id": "evt_current_subscription_item_period",
            "type": "customer.subscription.updated",
            "created": timestamp,
            "data": {
                "object": {
                    "id": "sub_current_period_shape",
                    "object": "subscription",
                    "customer": "cus_current_period_shape",
                    "status": "active",
                    "cancel_at_period_end": True,
                    "metadata": {"organization_id": organization_id},
                    "items": {
                        "data": [
                            {
                                "price": {"id": "price_growth"},
                                "current_period_end": later_period_end,
                            },
                            {
                                "price": {"id": "price_growth"},
                                "current_period_end": earliest_period_end,
                            },
                            {
                                "price": {"id": "price_growth"},
                                "current_period_end": {"malformed": True},
                            },
                        ]
                    },
                }
            },
        }

        response = _post_event(client, event, timestamp)

        assert response.status_code == 200
        db_session.expire_all()
        organization = db_session.get(Organization, organization_id)
        assert organization.billing_cancel_at_period_end is True
        assert organization.billing_current_period_end is not None
        assert int(
            stripe_billing_service._as_utc(
                organization.billing_current_period_end
            ).timestamp()
        ) == earliest_period_end
    finally:
        _clear_stripe(monkeypatch)


def test_webhook_locks_resolved_organization_before_validation_and_apply(
    client, db_session, monkeypatch
) -> None:
    _configure_stripe(monkeypatch)
    sequence: list[str] = []
    original_lock = stripe_billing_service._lock_organization
    original_validate = stripe_billing_service._validate_event_against_locked_organization
    original_apply = stripe_billing_service._apply_event

    def tracking_lock(db, organization_id):
        sequence.append("lock")
        return original_lock(db, organization_id)

    def tracking_validate(organization, *, event_type, obj):
        assert sequence == ["lock"]
        sequence.append("validate")
        return original_validate(organization, event_type=event_type, obj=obj)

    def tracking_apply(db, *, organization, event_type, event_created, obj):
        assert sequence == ["lock", "validate"]
        sequence.append("apply")
        return original_apply(
            db,
            organization=organization,
            event_type=event_type,
            event_created=event_created,
            obj=obj,
        )

    monkeypatch.setattr(stripe_billing_service, "_lock_organization", tracking_lock)
    monkeypatch.setattr(
        stripe_billing_service,
        "_validate_event_against_locked_organization",
        tracking_validate,
    )
    monkeypatch.setattr(stripe_billing_service, "_apply_event", tracking_apply)
    try:
        _token, organization_id = _login(client, "org-owner@example.com", "pass-org-owner")
        organization = db_session.get(Organization, organization_id)
        organization.plan_type = "multi_location"
        organization.stripe_customer_id = "cus_locked_webhook"
        organization.stripe_subscription_id = "sub_locked_webhook"
        organization.billing_status = "active"
        organization.billing_subscription_status = "active"
        db_session.commit()
        timestamp = int(time.time())
        event = {
            "id": "evt_locked_webhook",
            "type": "invoice.paid",
            "created": timestamp,
            "data": {
                "object": {
                    "id": "in_locked_webhook",
                    "object": "invoice",
                    "customer": "cus_locked_webhook",
                    "subscription": "sub_locked_webhook",
                }
            },
        }

        response = _post_event(client, event, timestamp)

        assert response.status_code == 200
        assert sequence == ["lock", "validate", "apply"]
    finally:
        _clear_stripe(monkeypatch)


@pytest.mark.parametrize("solo_first", [True, False])
def test_same_second_active_plan_updates_always_keep_lower_entitlement(
    client, db_session, monkeypatch, solo_first
) -> None:
    _configure_stripe(monkeypatch)
    try:
        _token, organization_id = _login(client, "org-owner@example.com", "pass-org-owner")
        organization = db_session.get(Organization, organization_id)
        organization.plan_type = "multi_location"
        organization.stripe_customer_id = "cus_same_second_plan"
        organization.stripe_subscription_id = "sub_same_second_plan"
        organization.stripe_price_id = "price_growth"
        organization.billing_status = "active"
        organization.billing_subscription_status = "active"
        organization.billing_subscription_event_type = "customer.subscription.updated"
        organization.billing_subscription_event_created_at = datetime.now(UTC) - timedelta(
            seconds=2
        )
        db_session.commit()
        timestamp = int(time.time())

        def plan_update(*, event_id: str, price_id: str) -> dict:
            return {
                "id": event_id,
                "type": "customer.subscription.updated",
                "created": timestamp,
                "data": {
                    "object": {
                        "id": "sub_same_second_plan",
                        "object": "subscription",
                        "customer": "cus_same_second_plan",
                        "status": "active",
                        "cancel_at_period_end": False,
                        "metadata": {"organization_id": organization_id},
                        "items": {"data": [{"price": {"id": price_id}}]},
                    }
                },
            }

        solo = plan_update(event_id=f"evt_same_second_solo_{solo_first}", price_id="price_solo")
        growth = plan_update(
            event_id=f"evt_same_second_growth_{solo_first}",
            price_id="price_growth",
        )
        ordered_events = [solo, growth] if solo_first else [growth, solo]

        responses = [_post_event(client, event, timestamp) for event in ordered_events]

        assert all(response.status_code == 200 for response in responses)
        db_session.expire_all()
        organization = db_session.get(Organization, organization_id)
        assert organization.plan_type == "solo"
        assert organization.stripe_price_id == "price_solo"
        assert organization.billing_subscription_status == "active"
        assert organization.billing_status == "active"
        if solo_first:
            assert responses[1].json()["data"]["status"] == "ignored"
            assert (
                responses[1].json()["data"]["duplicate"] is False
            )
    finally:
        _clear_stripe(monkeypatch)


def test_same_second_identical_subscription_update_is_a_safe_repeat(
    client, db_session, monkeypatch
) -> None:
    _configure_stripe(monkeypatch)
    try:
        _token, organization_id = _login(client, "org-owner@example.com", "pass-org-owner")
        organization = db_session.get(Organization, organization_id)
        organization.plan_type = "multi_location"
        organization.stripe_customer_id = "cus_same_second_repeat"
        organization.stripe_subscription_id = "sub_same_second_repeat"
        organization.stripe_price_id = "price_growth"
        organization.billing_status = "active"
        organization.billing_subscription_status = "active"
        organization.billing_subscription_event_type = "customer.subscription.updated"
        organization.billing_subscription_event_created_at = datetime.now(UTC) - timedelta(
            seconds=2
        )
        db_session.commit()
        timestamp = int(time.time())

        def repeat(event_id: str) -> dict:
            return {
                "id": event_id,
                "type": "customer.subscription.updated",
                "created": timestamp,
                "data": {
                    "object": {
                        "id": "sub_same_second_repeat",
                        "object": "subscription",
                        "customer": "cus_same_second_repeat",
                        "status": "active",
                        "cancel_at_period_end": False,
                        "metadata": {"organization_id": organization_id},
                        "items": {"data": [{"price": {"id": "price_growth"}}]},
                    }
                },
            }

        first = _post_event(client, repeat("evt_same_second_repeat_one"), timestamp)
        second = _post_event(client, repeat("evt_same_second_repeat_two"), timestamp)

        assert first.status_code == 200
        assert first.json()["data"]["status"] == "processed"
        assert second.status_code == 200
        assert second.json()["data"]["status"] == "ignored"
        db_session.expire_all()
        organization = db_session.get(Organization, organization_id)
        assert organization.plan_type == "multi_location"
        assert organization.stripe_price_id == "price_growth"
        assert organization.billing_status == "active"
    finally:
        _clear_stripe(monkeypatch)
