from __future__ import annotations

import hashlib
import hmac
import json
import threading
import time
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.models.audit_log import AuditLog
from app.models.billing import BillingWebhookEvent
from app.models.organization import Organization
from app.services import stripe_billing_service


pytestmark = pytest.mark.postgres_required


def _signature(raw_body: bytes, *, timestamp: int) -> str:
    digest = hmac.new(
        b"whsec_concurrency",
        f"{timestamp}.".encode() + raw_body,
        hashlib.sha256,
    ).hexdigest()
    return f"t={timestamp},v1={digest}"


def _plan_event(
    *,
    event_id: str,
    organization_id: str,
    timestamp: int,
    price_id: str,
) -> bytes:
    event = {
        "id": event_id,
        "type": "customer.subscription.updated",
        "created": timestamp,
        "data": {
            "object": {
                "id": "sub_concurrent_billing",
                "object": "subscription",
                "customer": "cus_concurrent_billing",
                "status": "active",
                "cancel_at_period_end": False,
                "metadata": {"organization_id": organization_id},
                "items": {"data": [{"price": {"id": price_id}}]},
            }
        },
    }
    return json.dumps(event, separators=(",", ":")).encode()


def _event_price_id(obj: dict) -> str:
    return str(obj.get("items", {}).get("data", [{}])[0].get("price", {}).get("id") or "")


def _paid_invoice_event(
    *,
    event_id: str,
    timestamp: int,
) -> bytes:
    event = {
        "id": event_id,
        "type": "invoice.paid",
        "created": timestamp,
        "data": {
            "object": {
                "id": "in_concurrent_retry",
                "object": "invoice",
                "customer": "cus_concurrent_retry",
                "parent": {
                    "type": "subscription_details",
                    "subscription_details": {
                        "subscription": "sub_concurrent_retry"
                    },
                },
            }
        },
    }
    return json.dumps(event, separators=(",", ":")).encode()


def test_postgres_webhooks_serialize_org_mutation_and_keep_receipts_truthful(
    apply_migrations,
    db_session,
    monkeypatch,
) -> None:
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_concurrency")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_concurrency")
    monkeypatch.setenv("STRIPE_PRICE_SOLO", "price_solo")
    monkeypatch.setenv("STRIPE_PRICE_GROWTH", "price_growth")
    get_settings.cache_clear()

    organization = db_session.query(Organization).order_by(Organization.id).first()
    assert organization is not None
    organization.plan_type = "multi_location"
    organization.stripe_customer_id = "cus_concurrent_billing"
    organization.stripe_subscription_id = "sub_concurrent_billing"
    organization.stripe_price_id = "price_growth"
    organization.billing_status = "active"
    organization.billing_subscription_status = "active"
    organization.billing_subscription_event_type = "customer.subscription.updated"
    organization.billing_subscription_event_created_at = datetime.now(UTC) - timedelta(
        seconds=2
    )
    db_session.commit()
    organization_id = organization.id

    timestamp = int(time.time())
    growth_body = _plan_event(
        event_id="evt_concurrent_growth",
        organization_id=organization_id,
        timestamp=timestamp,
        price_id="price_growth",
    )
    solo_body = _plan_event(
        event_id="evt_concurrent_solo",
        organization_id=organization_id,
        timestamp=timestamp,
        price_id="price_solo",
    )

    growth_locked = threading.Event()
    release_growth = threading.Event()
    solo_resolved = threading.Event()
    solo_done = threading.Event()
    original_validate = stripe_billing_service._validate_event_against_locked_organization
    original_resolve = stripe_billing_service._resolve_organization_for_event

    def blocking_validate(organization, *, event_type, obj):
        original_validate(organization, event_type=event_type, obj=obj)
        if _event_price_id(obj) == "price_growth":
            growth_locked.set()
            if not release_growth.wait(timeout=5):
                raise AssertionError("Timed out waiting to release the locked Growth webhook")

    def tracking_resolve(db, *, obj):
        resolved = original_resolve(db, obj=obj)
        if _event_price_id(obj) == "price_solo":
            solo_resolved.set()
        return resolved

    monkeypatch.setattr(
        stripe_billing_service,
        "_validate_event_against_locked_organization",
        blocking_validate,
    )
    monkeypatch.setattr(
        stripe_billing_service,
        "_resolve_organization_for_event",
        tracking_resolve,
    )

    engine = create_engine(str(apply_migrations["database_url"]), pool_pre_ping=True)
    session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    results: dict[str, dict] = {}
    errors: list[BaseException] = []

    def worker(name: str, raw_body: bytes, done: threading.Event | None = None) -> None:
        session = session_local()
        try:
            results[name] = stripe_billing_service.process_webhook(
                session,
                raw_body=raw_body,
                signature_header=_signature(raw_body, timestamp=timestamp),
            )
        except BaseException as exc:  # pragma: no cover - asserted in the parent thread
            errors.append(exc)
        finally:
            session.close()
            if done is not None:
                done.set()

    growth_thread = threading.Thread(
        target=worker,
        args=("growth", growth_body),
        daemon=True,
    )
    solo_thread = threading.Thread(
        target=worker,
        args=("solo", solo_body, solo_done),
        daemon=True,
    )
    growth_thread.start()
    try:
        assert growth_locked.wait(timeout=5), "Growth webhook never acquired the org row lock"
        solo_thread.start()
        assert solo_resolved.wait(timeout=5), "Solo webhook never resolved the organization"
        assert not solo_done.wait(timeout=0.25), (
            "Solo webhook mutated the organization without waiting for the row lock"
        )
    finally:
        release_growth.set()
        growth_thread.join(timeout=5)
        if solo_thread.ident is not None:
            solo_thread.join(timeout=5)
        engine.dispose()
        get_settings.cache_clear()

    assert not growth_thread.is_alive()
    assert not solo_thread.is_alive()
    assert errors == []
    assert results["growth"]["status"] == "processed"
    assert results["solo"]["status"] == "processed"

    db_session.expire_all()
    organization = db_session.get(Organization, organization_id)
    assert organization is not None
    assert organization.plan_type == "solo"
    assert organization.stripe_price_id == "price_solo"
    receipts = (
        db_session.query(BillingWebhookEvent)
        .filter(
            BillingWebhookEvent.provider_event_id.in_(
                ["evt_concurrent_growth", "evt_concurrent_solo"]
            )
        )
        .all()
    )
    assert {receipt.status for receipt in receipts} == {"processed"}
    assert len(receipts) == 2


def test_postgres_concurrent_failed_receipt_retry_has_one_truthful_winner(
    apply_migrations,
    db_session,
    monkeypatch,
) -> None:
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_concurrency")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_concurrency")
    monkeypatch.setenv("STRIPE_PRICE_SOLO", "price_solo")
    monkeypatch.setenv("STRIPE_PRICE_GROWTH", "price_growth")
    get_settings.cache_clear()

    organization = db_session.query(Organization).order_by(Organization.id).first()
    assert organization is not None
    organization.plan_type = "multi_location"
    organization.stripe_customer_id = "cus_concurrent_retry"
    organization.stripe_subscription_id = "sub_concurrent_retry"
    organization.stripe_price_id = "price_growth"
    organization.billing_status = "past_due"
    organization.billing_subscription_status = "active"
    organization.billing_subscription_event_type = "customer.subscription.updated"
    organization.billing_subscription_event_created_at = datetime.now(UTC) - timedelta(
        minutes=1
    )
    organization.billing_payment_status = "past_due"
    organization.billing_payment_event_type = "invoice.payment_failed"
    organization.billing_payment_event_created_at = datetime.now(UTC) - timedelta(
        minutes=1
    )
    organization_id = organization.id
    timestamp = int(time.time())
    event_id = "evt_concurrent_failed_receipt_retry"
    raw_body = _paid_invoice_event(event_id=event_id, timestamp=timestamp)
    db_session.add(
        BillingWebhookEvent(
            provider_event_id=event_id,
            event_type="invoice.paid",
            organization_id=organization_id,
            event_created_at=datetime.fromtimestamp(timestamp, tz=UTC),
            object_id="in_concurrent_retry",
            payload_sha256=hashlib.sha256(raw_body).hexdigest(),
            status="failed",
            attempt_count=1,
            error_code="billing_event_processing_failed",
            processed_at=datetime.now(UTC),
        )
    )
    db_session.commit()

    first_in_apply_path = threading.Event()
    release_first = threading.Event()
    second_claim_started = threading.Event()
    second_done = threading.Event()
    original_lock_organization = stripe_billing_service._lock_organization
    original_locked_receipt = stripe_billing_service._locked_webhook_receipt

    def blocking_org_lock(db, requested_organization_id):
        locked = original_lock_organization(db, requested_organization_id)
        if threading.current_thread().name == "billing-retry-first":
            first_in_apply_path.set()
            if not release_first.wait(timeout=5):
                raise AssertionError("Timed out waiting to release the winning retry")
        return locked

    def tracking_receipt_lock(db, requested_event_id):
        if threading.current_thread().name == "billing-retry-second":
            second_claim_started.set()
        return original_locked_receipt(db, requested_event_id)

    monkeypatch.setattr(
        stripe_billing_service,
        "_lock_organization",
        blocking_org_lock,
    )
    monkeypatch.setattr(
        stripe_billing_service,
        "_locked_webhook_receipt",
        tracking_receipt_lock,
    )

    engine = create_engine(str(apply_migrations["database_url"]), pool_pre_ping=True)
    session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    results: dict[str, dict] = {}
    errors: list[BaseException] = []

    def worker(name: str, done: threading.Event | None = None) -> None:
        session = session_local()
        try:
            results[name] = stripe_billing_service.process_webhook(
                session,
                raw_body=raw_body,
                signature_header=_signature(raw_body, timestamp=timestamp),
            )
        except BaseException as exc:  # pragma: no cover - asserted in the parent thread
            errors.append(exc)
        finally:
            session.close()
            if done is not None:
                done.set()

    first_thread = threading.Thread(
        target=worker,
        args=("first",),
        name="billing-retry-first",
        daemon=True,
    )
    second_thread = threading.Thread(
        target=worker,
        args=("second", second_done),
        name="billing-retry-second",
        daemon=True,
    )
    first_thread.start()
    try:
        assert first_in_apply_path.wait(timeout=5), (
            "First retry never claimed the failed receipt"
        )
        second_thread.start()
        assert second_claim_started.wait(timeout=5), (
            "Second retry never attempted to claim the receipt"
        )
        assert not second_done.wait(timeout=0.25), (
            "Second retry bypassed the receipt row lock"
        )
    finally:
        release_first.set()
        first_thread.join(timeout=5)
        if second_thread.ident is not None:
            second_thread.join(timeout=5)
        engine.dispose()
        get_settings.cache_clear()

    assert not first_thread.is_alive()
    assert not second_thread.is_alive()
    assert errors == []
    assert results["first"] == {
        "received": True,
        "duplicate": False,
        "status": "processed",
    }
    assert results["second"] == {
        "received": True,
        "duplicate": True,
        "status": "processed",
    }

    db_session.expire_all()
    receipt = (
        db_session.query(BillingWebhookEvent)
        .filter(BillingWebhookEvent.provider_event_id == event_id)
        .one()
    )
    organization = db_session.get(Organization, organization_id)
    assert organization is not None
    assert receipt.status == "processed"
    assert receipt.attempt_count == 2
    assert receipt.error_code is None
    assert organization.billing_payment_status == "paid"
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
