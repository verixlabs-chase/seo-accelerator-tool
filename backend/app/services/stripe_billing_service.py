from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.billing import BillingWebhookEvent
from app.models.organization import Organization
from app.services.audit_service import write_audit_log
from app.services.cost_economics_service import resolve_plan_economics


ACTIVE_STATUSES = {"active", "trialing"}
ACCESS_ENDING_STATUSES = {"canceled", "unpaid", "incomplete_expired"}
RECOVERY_STATUSES = {"past_due", "payment_action_required", "unpaid"}


class BillingError(Exception):
    def __init__(self, message: str, *, reason_code: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.status_code = status_code


def get_billing_summary(organization: Organization) -> dict[str, Any]:
    settings = get_settings()
    plan = resolve_plan_economics(organization.plan_type)
    status = organization.billing_status or "not_started"
    configured_prices = {
        "solo": bool(settings.stripe_price_solo.strip()),
        "multi_location": bool(settings.stripe_price_growth.strip()),
    }
    configured = bool(settings.stripe_secret_key.strip())
    recovery_message = None
    if status in RECOVERY_STATUSES:
        recovery_message = (
            "Your latest payment needs attention. Update the payment method to keep every "
            "included feature running. Your saved work has not been removed."
        )
    return {
        "provider_configured": configured,
        "plan_code": plan.code,
        "plan_name": plan.name,
        "status": status,
        "status_label": _status_label(status),
        "portal_available": configured and bool(organization.stripe_customer_id),
        "checkout_available": configured and configured_prices.get(plan.code, False),
        "available_checkout_plans": [
            code for code, available in configured_prices.items() if configured and available
        ],
        "current_period_end": _iso(organization.billing_current_period_end),
        "cancel_at_period_end": bool(organization.billing_cancel_at_period_end),
        "recovery_message": recovery_message,
    }


def create_checkout_session(
    db: Session,
    *,
    organization: Organization,
    requested_plan_code: str,
    actor_user_id: str,
) -> dict[str, Any]:
    if organization.billing_mode != "subscription":
        raise BillingError(
            "This organization uses custom billing. Contact support to change its plan.",
            reason_code="custom_billing_managed_by_support",
            status_code=409,
        )
    if organization.stripe_subscription_id and organization.billing_status not in ACCESS_ENDING_STATUSES:
        raise BillingError(
            "A subscription already exists. Use Manage billing to change it safely.",
            reason_code="subscription_already_exists",
            status_code=409,
        )
    requested_plan = resolve_plan_economics(requested_plan_code)
    if requested_plan.code == "enterprise":
        raise BillingError(
            "Enterprise plans are prepared with custom terms. Contact support to continue.",
            reason_code="enterprise_requires_custom_terms",
            status_code=409,
        )
    price_id = _price_id_for_plan(requested_plan.code)
    app_base = _customer_app_base_url()
    fields: list[tuple[str, str]] = [
        ("mode", "subscription"),
        ("line_items[0][price]", price_id),
        ("line_items[0][quantity]", "1"),
        ("allow_promotion_codes", "true"),
        ("success_url", f"{app_base}/settings?billing=success&session_id={{CHECKOUT_SESSION_ID}}"),
        ("cancel_url", f"{app_base}/settings?billing=cancelled"),
        ("client_reference_id", organization.id),
        ("metadata[organization_id]", organization.id),
        ("metadata[requested_plan_code]", requested_plan.code),
        ("subscription_data[metadata][organization_id]", organization.id),
        ("subscription_data[metadata][plan_code]", requested_plan.code),
    ]
    if organization.stripe_customer_id:
        fields.append(("customer", organization.stripe_customer_id))
    payload = _stripe_post(
        "/checkout/sessions",
        fields,
        idempotency_key=f"checkout-{organization.id}-{requested_plan.code}-{uuid.uuid4()}",
    )
    url = str(payload.get("url") or "").strip()
    if not url:
        raise BillingError(
            "The secure checkout link was not created. Please try again.",
            reason_code="checkout_url_missing",
            status_code=502,
        )
    write_audit_log(
        db,
        tenant_id=organization.id,
        actor_user_id=actor_user_id,
        event_type="billing.checkout.created",
        payload={
            "organization_id": organization.id,
            "requested_plan_code": requested_plan.code,
            "checkout_session_id": payload.get("id"),
        },
    )
    return {
        "url": url,
        "session_id": payload.get("id"),
        "expires_at": _timestamp_iso(payload.get("expires_at")),
    }


def create_customer_portal_session(
    db: Session,
    *,
    organization: Organization,
    actor_user_id: str,
) -> dict[str, Any]:
    if not organization.stripe_customer_id:
        raise BillingError(
            "No billing account is connected yet.",
            reason_code="billing_customer_not_found",
            status_code=409,
        )
    payload = _stripe_post(
        "/billing_portal/sessions",
        [
            ("customer", organization.stripe_customer_id),
            ("return_url", f"{_customer_app_base_url()}/settings"),
        ],
        idempotency_key=f"portal-{organization.id}-{uuid.uuid4()}",
    )
    url = str(payload.get("url") or "").strip()
    if not url:
        raise BillingError(
            "The secure billing link was not created. Please try again.",
            reason_code="billing_portal_url_missing",
            status_code=502,
        )
    write_audit_log(
        db,
        tenant_id=organization.id,
        actor_user_id=actor_user_id,
        event_type="billing.portal.created",
        payload={"organization_id": organization.id},
    )
    return {"url": url}


def verify_webhook_signature(
    raw_body: bytes,
    signature_header: str,
    *,
    now_timestamp: int | None = None,
) -> int:
    settings = get_settings()
    secret = settings.stripe_webhook_secret.strip()
    if not secret:
        raise BillingError(
            "Billing webhook verification is not configured.",
            reason_code="billing_webhook_not_configured",
            status_code=503,
        )
    parts: dict[str, list[str]] = {}
    for item in signature_header.split(","):
        key, separator, value = item.strip().partition("=")
        if separator and key and value:
            parts.setdefault(key, []).append(value)
    try:
        timestamp = int(parts.get("t", [""])[0])
    except ValueError as exc:
        raise BillingError(
            "The billing event signature is invalid.",
            reason_code="invalid_billing_webhook_signature",
            status_code=400,
        ) from exc
    signatures = parts.get("v1", [])
    expected = hmac.new(
        secret.encode("utf-8"),
        f"{timestamp}.".encode("utf-8") + raw_body,
        hashlib.sha256,
    ).hexdigest()
    if not signatures or not any(hmac.compare_digest(expected, value) for value in signatures):
        raise BillingError(
            "The billing event signature is invalid.",
            reason_code="invalid_billing_webhook_signature",
            status_code=400,
        )
    current = int(time.time()) if now_timestamp is None else now_timestamp
    if abs(current - timestamp) > settings.stripe_webhook_tolerance_seconds:
        raise BillingError(
            "The billing event is too old to process safely.",
            reason_code="stale_billing_webhook",
            status_code=400,
        )
    return timestamp


def process_webhook(db: Session, *, raw_body: bytes, signature_header: str) -> dict[str, Any]:
    verify_webhook_signature(raw_body, signature_header)
    try:
        event = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise BillingError(
            "The billing event body is invalid.",
            reason_code="invalid_billing_webhook_body",
        ) from exc
    event_id = str(event.get("id") or "").strip()
    event_type = str(event.get("type") or "").strip()
    event_created = _event_datetime(event.get("created"))
    obj = event.get("data", {}).get("object", {})
    if not event_id or not event_type or not isinstance(obj, dict):
        raise BillingError(
            "The billing event is missing required fields.",
            reason_code="invalid_billing_webhook_body",
        )
    receipt = (
        db.query(BillingWebhookEvent)
        .filter(BillingWebhookEvent.provider_event_id == event_id)
        .one_or_none()
    )
    if receipt and receipt.status in {"processed", "ignored", "processing"}:
        return {"received": True, "duplicate": True, "status": receipt.status}
    if receipt is None:
        receipt = BillingWebhookEvent(
            provider_event_id=event_id,
            event_type=event_type,
            api_version=event.get("api_version"),
            event_created_at=event_created,
            object_id=str(obj.get("id") or "") or None,
            payload_sha256=hashlib.sha256(raw_body).hexdigest(),
            status="processing",
            attempt_count=1,
        )
        db.add(receipt)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return {"received": True, "duplicate": True, "status": "processed"}
    else:
        receipt.status = "processing"
        receipt.attempt_count += 1
        receipt.error_code = None

    try:
        organization = _organization_for_event(db, obj)
        if organization is None:
            receipt.status = "ignored"
            receipt.error_code = "organization_not_found"
        elif (
            organization.billing_last_event_created_at
            and _as_utc(organization.billing_last_event_created_at) > event_created
        ):
            receipt.organization_id = organization.id
            receipt.status = "ignored"
            receipt.error_code = "older_than_saved_billing_state"
        else:
            receipt.organization_id = organization.id
            # A malformed or unknown subscription must not leave partial customer,
            # subscription, or status changes behind while we retain the failed receipt.
            with db.begin_nested():
                _apply_event(db, organization=organization, event_type=event_type, obj=obj)
                organization.billing_last_event_created_at = event_created
            receipt.status = "processed"
        receipt.processed_at = datetime.now(UTC)
        db.commit()
    except BillingError as exc:
        receipt.status = "failed"
        receipt.error_code = exc.reason_code
        receipt.processed_at = datetime.now(UTC)
        db.commit()
        raise
    except Exception as exc:
        db.rollback()
        raise BillingError(
            "The billing event could not be processed yet.",
            reason_code="billing_event_processing_failed",
            status_code=503,
        ) from exc
    return {"received": True, "duplicate": False, "status": receipt.status}


def _apply_event(
    db: Session,
    *,
    organization: Organization,
    event_type: str,
    obj: dict[str, Any],
) -> None:
    before = {
        "plan_type": organization.plan_type,
        "billing_status": organization.billing_status,
        "cancel_at_period_end": bool(organization.billing_cancel_at_period_end),
    }
    if event_type == "checkout.session.completed":
        _assign_external_id(organization, "stripe_customer_id", obj.get("customer"))
        _assign_external_id(organization, "stripe_subscription_id", obj.get("subscription"))
        organization.billing_status = "checkout_completed"
    elif event_type.startswith("customer.subscription."):
        _assign_external_id(organization, "stripe_customer_id", obj.get("customer"))
        _assign_external_id(organization, "stripe_subscription_id", obj.get("id"))
        status = str(obj.get("status") or "unknown")
        organization.billing_status = status
        organization.billing_cancel_at_period_end = bool(obj.get("cancel_at_period_end"))
        organization.billing_current_period_end = _optional_event_datetime(
            obj.get("current_period_end")
        )
        price_id = _subscription_price_id(obj)
        if price_id:
            organization.stripe_price_id = price_id
        if status in ACTIVE_STATUSES:
            plan_code = _plan_for_subscription(obj, price_id)
            organization.plan_type = plan_code
            organization.billing_last_error_code = None
        elif status in ACCESS_ENDING_STATUSES:
            organization.plan_type = "solo"
            organization.billing_last_error_code = "subscription_ended"
    elif event_type == "invoice.payment_failed":
        organization.billing_status = "past_due"
        organization.billing_last_error_code = "payment_failed"
    elif event_type == "invoice.payment_action_required":
        organization.billing_status = "payment_action_required"
        organization.billing_last_error_code = "payment_action_required"
    elif event_type == "invoice.paid":
        organization.billing_status = "active"
        organization.billing_last_error_code = None
    else:
        return
    after = {
        "plan_type": organization.plan_type,
        "billing_status": organization.billing_status,
        "cancel_at_period_end": bool(organization.billing_cancel_at_period_end),
    }
    write_audit_log(
        db,
        tenant_id=organization.id,
        actor_user_id=None,
        event_type="billing.state.updated",
        payload={
            "organization_id": organization.id,
            "provider_event_type": event_type,
            "before": before,
            "after": after,
        },
    )


def _organization_for_event(db: Session, obj: dict[str, Any]) -> Organization | None:
    metadata = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
    metadata_org_id = str(metadata.get("organization_id") or "").strip()
    reference_org_id = str(obj.get("client_reference_id") or "").strip()
    if metadata_org_id and reference_org_id and metadata_org_id != reference_org_id:
        raise BillingError(
            "The billing event organization identifiers do not agree.",
            reason_code="billing_organization_mismatch",
        )
    organization = db.get(Organization, metadata_org_id or reference_org_id) if (metadata_org_id or reference_org_id) else None
    customer_id = str(obj.get("customer") or "").strip()
    subscription_id = str(obj.get("subscription") or "").strip()
    if not subscription_id and str(obj.get("object") or "") == "subscription":
        subscription_id = str(obj.get("id") or "").strip()
    if organization is None and customer_id:
        organization = (
            db.query(Organization).filter(Organization.stripe_customer_id == customer_id).one_or_none()
        )
    if organization is None and subscription_id:
        organization = (
            db.query(Organization)
            .filter(Organization.stripe_subscription_id == subscription_id)
            .one_or_none()
        )
    if organization and customer_id and organization.stripe_customer_id not in {None, customer_id}:
        raise BillingError(
            "The billing customer does not match this organization.",
            reason_code="billing_customer_mismatch",
        )
    return organization


def _plan_for_subscription(obj: dict[str, Any], price_id: str | None) -> str:
    if not price_id:
        raise BillingError(
            "The subscription does not contain a supported plan price.",
            reason_code="billing_price_missing",
        )
    derived = _plan_code_for_price(price_id)
    metadata = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
    requested = str(metadata.get("plan_code") or "").strip()
    if requested and resolve_plan_economics(requested).code != derived:
        raise BillingError(
            "The subscription plan does not match its configured price.",
            reason_code="billing_plan_price_mismatch",
        )
    return derived


def _subscription_price_id(obj: dict[str, Any]) -> str | None:
    items = obj.get("items", {}).get("data", [])
    if not isinstance(items, list) or not items:
        return None
    price = items[0].get("price", {}) if isinstance(items[0], dict) else {}
    return str(price.get("id") or "").strip() or None


def _price_id_for_plan(plan_code: str) -> str:
    settings = get_settings()
    value = settings.stripe_price_solo if plan_code == "solo" else settings.stripe_price_growth
    if not value.strip():
        raise BillingError(
            "Secure checkout is not configured for this plan yet.",
            reason_code="billing_price_not_configured",
            status_code=503,
        )
    return value.strip()


def _plan_code_for_price(price_id: str) -> str:
    settings = get_settings()
    configured = {
        settings.stripe_price_solo.strip(): "solo",
        settings.stripe_price_growth.strip(): "multi_location",
    }
    plan_code = configured.get(price_id)
    if not plan_code:
        raise BillingError(
            "The subscription price is not recognized.",
            reason_code="billing_price_not_supported",
        )
    return plan_code


def _stripe_post(
    path: str,
    fields: list[tuple[str, str]],
    *,
    idempotency_key: str,
) -> dict[str, Any]:
    settings = get_settings()
    secret = settings.stripe_secret_key.strip()
    if not secret:
        raise BillingError(
            "Secure billing is not configured yet.",
            reason_code="billing_not_configured",
            status_code=503,
        )
    try:
        response = httpx.post(
            f"{settings.stripe_api_base_url.rstrip('/')}{path}",
            data=fields,
            headers={
                "Authorization": f"Bearer {secret}",
                "Idempotency-Key": idempotency_key,
            },
            timeout=settings.stripe_http_timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise BillingError(
            "The billing service could not be reached. Please try again.",
            reason_code="billing_provider_unavailable",
            status_code=502,
        ) from exc
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if response.status_code >= 400:
        raise BillingError(
            "The billing service could not complete that request.",
            reason_code="billing_provider_rejected_request",
            status_code=502,
        )
    return payload


def _customer_app_base_url() -> str:
    settings = get_settings()
    raw = (settings.customer_app_base_url or settings.public_base_url).strip().rstrip("/")
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise BillingError(
            "The customer application URL is not configured safely.",
            reason_code="customer_app_url_invalid",
            status_code=503,
        )
    return raw


def _assign_external_id(organization: Organization, attribute: str, value: Any) -> None:
    normalized = str(value or "").strip()
    if not normalized:
        return
    current = getattr(organization, attribute)
    if current and current != normalized:
        raise BillingError(
            "The billing account identifiers do not match this organization.",
            reason_code="billing_external_id_mismatch",
        )
    setattr(organization, attribute, normalized)


def _event_datetime(value: Any) -> datetime:
    try:
        return datetime.fromtimestamp(int(value), tz=UTC)
    except (TypeError, ValueError, OSError) as exc:
        raise BillingError(
            "The billing event timestamp is invalid.",
            reason_code="invalid_billing_event_timestamp",
        ) from exc


def _optional_event_datetime(value: Any) -> datetime | None:
    if value in {None, ""}:
        return None
    return _event_datetime(value)


def _timestamp_iso(value: Any) -> str | None:
    parsed = _optional_event_datetime(value)
    return parsed.isoformat() if parsed else None


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _iso(value: datetime | None) -> str | None:
    return _as_utc(value).isoformat() if value else None


def _status_label(status: str) -> str:
    labels = {
        "not_started": "No subscription yet",
        "checkout_completed": "Payment received; confirming plan",
        "trialing": "Trial active",
        "active": "Active",
        "past_due": "Payment needs attention",
        "payment_action_required": "Payment confirmation needed",
        "canceled": "Canceled",
        "unpaid": "Payment overdue",
    }
    return labels.get(status, status.replace("_", " ").strip().title())
