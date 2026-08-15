from __future__ import annotations

import hashlib
import hmac
import json
import re
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
from app.services.commercial_plan_service import apply_commercial_plan
from app.services.cost_economics_service import CostEconomicsError, resolve_plan_economics


ACTIVE_STATUSES = {"active", "trialing"}
ACCESS_ENDING_STATUSES = {"canceled", "unpaid", "incomplete_expired"}
RECOVERY_STATUSES = {"past_due", "payment_action_required", "unpaid"}
SUPPORTED_WEBHOOK_EVENT_TYPES = {
    "checkout.session.completed",
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "invoice.paid",
    "invoice.payment_action_required",
    "invoice.payment_failed",
}
AUTHORITATIVE_STATE_EVENT_TYPES = {
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
}
CHECKOUT_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")
DUPLICATE_RECEIPT_STATUSES = {"processed", "ignored", "processing"}


class BillingError(Exception):
    def __init__(self, message: str, *, reason_code: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.status_code = status_code


def get_billing_summary(organization: Organization) -> dict[str, Any]:
    plan = resolve_plan_economics(organization.plan_type)
    status = organization.billing_status or "not_started"
    readiness = get_billing_readiness(organization)
    recovery_message = None
    if status in RECOVERY_STATUSES:
        recovery_message = (
            "Your latest payment needs attention. Update the payment method to keep every "
            "included feature running. Your saved work has not been removed."
        )
    return {
        "provider_configured": readiness["provider_configured"],
        "plan_code": plan.code,
        "plan_name": plan.name,
        "status": status,
        "status_label": _status_label(status),
        "portal_available": readiness["portal_configured"],
        "checkout_available": plan.code in readiness["configured_plan_codes"],
        "available_checkout_plans": readiness["configured_plan_codes"],
        "current_period_end": _iso(organization.billing_current_period_end),
        "cancel_at_period_end": bool(organization.billing_cancel_at_period_end),
        "recovery_message": recovery_message,
        "readiness": readiness,
        "checkout_confirmation": _checkout_confirmation(organization),
        "pending_checkout": _pending_checkout_summary(organization),
    }


def get_billing_readiness(organization: Organization) -> dict[str, Any]:
    """Return saved configuration facts without contacting the billing provider."""

    settings = get_settings()
    provider_configured = bool(settings.stripe_secret_key.strip())
    configured_prices = {
        "solo": bool(settings.stripe_price_solo.strip()),
        "multi_location": bool(settings.stripe_price_growth.strip()),
    }
    configured_plan_codes = [
        code
        for code, price_configured in configured_prices.items()
        if provider_configured and price_configured
    ]
    return {
        "source": "saved_configuration",
        "network_checked": False,
        "billing_mode": organization.billing_mode,
        "provider_configured": provider_configured,
        "webhook_configured": bool(settings.stripe_webhook_secret.strip()),
        "checkout_configured": bool(configured_plan_codes),
        "portal_configured": provider_configured and bool(organization.stripe_customer_id),
        "configured_plan_codes": configured_plan_codes,
    }


def create_checkout_session(
    db: Session,
    *,
    organization: Organization,
    requested_plan_code: str,
    client_request_id: str,
    actor_user_id: str,
) -> dict[str, Any]:
    organization = _lock_organization(db, organization.id)
    if organization.billing_mode != "subscription":
        raise BillingError(
            "This organization uses custom billing. Contact support to change its plan.",
            reason_code="custom_billing_managed_by_support",
            status_code=409,
        )
    if (
        organization.stripe_subscription_id
        and _current_subscription_status(organization) not in ACCESS_ENDING_STATUSES
    ):
        raise BillingError(
            "A subscription already exists. Use Manage billing to change it safely.",
            reason_code="subscription_already_exists",
            status_code=409,
        )
    requested_plan = resolve_plan_economics(requested_plan_code)
    normalized_request_id = _validate_checkout_request_id(client_request_id)
    if requested_plan.code == "enterprise":
        raise BillingError(
            "Enterprise plans are prepared with custom terms. Contact support to continue.",
            reason_code="enterprise_requires_custom_terms",
            status_code=409,
        )
    price_id = _price_id_for_plan(requested_plan.code)
    now = datetime.now(UTC)
    pending_active = _pending_checkout_is_active(organization, now=now)
    reuse_pending = False
    if pending_active:
        if (
            organization.billing_pending_checkout_request_id != normalized_request_id
            or organization.billing_pending_checkout_plan_code != requested_plan.code
        ):
            raise BillingError(
                "Another secure checkout is already open. Finish it or wait for it to expire.",
                reason_code="checkout_already_pending",
                status_code=409,
            )
        reuse_pending = True
    elif organization.billing_pending_checkout_request_id:
        _clear_pending_checkout(organization)

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
        ("metadata[client_request_id]", normalized_request_id),
        ("subscription_data[metadata][organization_id]", organization.id),
        ("subscription_data[metadata][plan_code]", requested_plan.code),
        ("subscription_data[metadata][client_request_id]", normalized_request_id),
    ]
    if organization.stripe_customer_id:
        fields.append(("customer", organization.stripe_customer_id))
    payload = _stripe_post(
        "/checkout/sessions",
        fields,
        idempotency_key=_checkout_idempotency_key(
            organization_id=organization.id,
            plan_code=requested_plan.code,
            client_request_id=normalized_request_id,
        ),
    )
    url = str(payload.get("url") or "").strip()
    if not url:
        raise BillingError(
            "The secure checkout link was not created. Please try again.",
            reason_code="checkout_url_missing",
            status_code=502,
        )
    session_id = str(payload.get("id") or "").strip()
    expires_at = _optional_event_datetime(payload.get("expires_at"))
    if not session_id or expires_at is None:
        raise BillingError(
            "The secure checkout did not include the confirmation details needed to track it.",
            reason_code="checkout_confirmation_details_missing",
            status_code=502,
        )
    if expires_at <= now:
        raise BillingError(
            "That secure checkout has expired. Start a new checkout to continue.",
            reason_code="checkout_session_expired",
            status_code=409,
        )
    if reuse_pending and session_id != organization.billing_pending_checkout_session_id:
        raise BillingError(
            "The secure checkout retry did not match the saved checkout.",
            reason_code="checkout_session_conflict",
            status_code=409,
        )
    if not reuse_pending:
        organization.billing_pending_checkout_request_id = normalized_request_id
        organization.billing_pending_checkout_session_id = session_id
        organization.billing_pending_checkout_plan_code = requested_plan.code
        organization.billing_pending_checkout_expires_at = expires_at
    write_audit_log(
        db,
        tenant_id=organization.id,
        actor_user_id=actor_user_id,
        event_type=("billing.checkout.reopened" if reuse_pending else "billing.checkout.created"),
        payload={
            "organization_id": organization.id,
            "requested_plan_code": requested_plan.code,
            "client_request_id": normalized_request_id,
            "checkout_session_id": session_id,
            "expires_at": expires_at.isoformat(),
        },
    )
    return {
        "url": url,
        "session_id": session_id,
        "expires_at": expires_at.isoformat(),
        "client_request_id": normalized_request_id,
        "requested_plan_code": requested_plan.code,
        "checkout_status": "reused" if reuse_pending else "created",
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
    payload_sha256 = hashlib.sha256(raw_body).hexdigest()
    receipt, duplicate_result = _claim_webhook_receipt(
        db,
        event_id=event_id,
        event_type=event_type,
        api_version=event.get("api_version"),
        event_created=event_created,
        object_id=_provider_object_id(obj.get("id")) or None,
        payload_sha256=payload_sha256,
    )
    if duplicate_result is not None:
        return duplicate_result

    try:
        if event_type not in SUPPORTED_WEBHOOK_EVENT_TYPES:
            receipt.status = "ignored"
            receipt.error_code = "unsupported_billing_event_type"
            receipt.processed_at = datetime.now(UTC)
            db.commit()
            return {"received": True, "duplicate": False, "status": receipt.status}
        organization = _resolve_organization_for_event(db, obj=obj)
        if organization is None:
            receipt.status = "ignored"
            receipt.error_code = "organization_not_found"
        else:
            # Serialize every provider mutation for this organization. Resolution is
            # intentionally read-only; all correlation, ordering, and apply checks run
            # against the row refreshed under this transaction-scoped lock.
            organization = _lock_organization(db, organization.id)
            receipt.organization_id = organization.id
            _validate_event_against_locked_organization(
                organization,
                event_type=event_type,
                obj=obj,
            )
            # A malformed or unknown subscription must not leave partial customer,
            # subscription, or status changes behind while we retain the failed receipt.
            with db.begin_nested():
                ignored_reason = _apply_event(
                    db,
                    organization=organization,
                    event_type=event_type,
                    event_created=event_created,
                    obj=obj,
                )
            if ignored_reason:
                receipt.status = "ignored"
                receipt.error_code = ignored_reason
            else:
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


def _claim_webhook_receipt(
    db: Session,
    *,
    event_id: str,
    event_type: str,
    api_version: Any,
    event_created: datetime,
    object_id: str | None,
    payload_sha256: str,
) -> tuple[BillingWebhookEvent, dict[str, Any] | None]:
    receipt = _locked_webhook_receipt(db, event_id)
    if receipt is not None:
        return _claim_existing_webhook_receipt(
            db,
            receipt=receipt,
            payload_sha256=payload_sha256,
        )

    receipt = BillingWebhookEvent(
        provider_event_id=event_id,
        event_type=event_type,
        api_version=api_version,
        event_created_at=event_created,
        object_id=object_id,
        payload_sha256=payload_sha256,
        status="processing",
        attempt_count=1,
    )
    db.add(receipt)
    try:
        db.flush()
    except IntegrityError as exc:
        # Another transaction inserted this event ID after our initial read. Roll
        # back the losing insert, lock the winner, and re-evaluate its committed truth.
        db.rollback()
        receipt = _locked_webhook_receipt(db, event_id)
        if receipt is None:
            raise BillingError(
                "The billing event receipt could not be confirmed safely.",
                reason_code="billing_event_receipt_conflict",
                status_code=503,
            ) from exc
        return _claim_existing_webhook_receipt(
            db,
            receipt=receipt,
            payload_sha256=payload_sha256,
        )
    return receipt, None


def _locked_webhook_receipt(
    db: Session,
    event_id: str,
) -> BillingWebhookEvent | None:
    return (
        db.query(BillingWebhookEvent)
        .filter(BillingWebhookEvent.provider_event_id == event_id)
        .populate_existing()
        .with_for_update()
        .one_or_none()
    )


def _claim_existing_webhook_receipt(
    db: Session,
    *,
    receipt: BillingWebhookEvent,
    payload_sha256: str,
) -> tuple[BillingWebhookEvent, dict[str, Any] | None]:
    try:
        _require_matching_webhook_payload(receipt, payload_sha256)
    except BillingError:
        db.rollback()
        raise
    if receipt.status in DUPLICATE_RECEIPT_STATUSES:
        duplicate_result = {
            "received": True,
            "duplicate": True,
            "status": receipt.status,
        }
        # Release the receipt row lock before returning the duplicate response.
        db.commit()
        return receipt, duplicate_result
    receipt.status = "processing"
    receipt.attempt_count = int(receipt.attempt_count or 0) + 1
    receipt.error_code = None
    receipt.processed_at = None
    return receipt, None


def _apply_event(
    db: Session,
    *,
    organization: Organization,
    event_type: str,
    event_created: datetime,
    obj: dict[str, Any],
) -> str | None:
    before = {
        "plan_type": organization.plan_type,
        "billing_status": organization.billing_status,
        "cancel_at_period_end": bool(organization.billing_cancel_at_period_end),
    }
    if event_type == "checkout.session.completed":
        _assign_external_id(
            organization,
            "stripe_customer_id",
            _provider_object_id(obj.get("customer")),
        )
        _assign_subscription_id(
            db,
            organization=organization,
            event_type=event_type,
            obj=obj,
            value=_provider_object_id(obj.get("subscription")),
        )
        _confirm_checkout(organization, obj=obj)
        _refresh_derived_billing_state(organization)
    elif event_type in AUTHORITATIVE_STATE_EVENT_TYPES:
        _assign_external_id(
            organization,
            "stripe_customer_id",
            _provider_object_id(obj.get("customer")),
        )
        rotated = _assign_subscription_id(
            db,
            organization=organization,
            event_type=event_type,
            obj=obj,
            value=obj.get("id"),
        )
        status = (
            "canceled"
            if event_type == "customer.subscription.deleted"
            else str(obj.get("status") or "unknown")
        )
        price_id = _subscription_price_id(obj)
        created_plan_code = None
        incoming_plan_code = None
        if event_type == "customer.subscription.created":
            created_plan_code = _plan_for_subscription(price_id)
            _require_created_subscription_plan_match(
                obj,
                price_plan_code=created_plan_code,
            )
        if status in ACTIVE_STATUSES:
            incoming_plan_code = created_plan_code or _plan_for_subscription(price_id)
        if not _should_apply_subscription_event(
            organization,
            event_type=event_type,
            event_created=event_created,
            incoming_status=status,
            incoming_plan_code=incoming_plan_code,
            rotated=rotated,
        ):
            return "older_or_lower_priority_subscription_event"
        organization.billing_cancel_at_period_end = bool(obj.get("cancel_at_period_end"))
        organization.billing_current_period_end = _subscription_current_period_end(obj)
        if price_id:
            organization.stripe_price_id = price_id
        # Commercial plan materialization intentionally refreshes and locks
        # the Organization row. Flush the verified provider identifiers first
        # so that refresh cannot discard these same-transaction assignments.
        db.flush()
        if status in ACTIVE_STATUSES:
            plan_code = incoming_plan_code
            if plan_code is None:
                raise BillingError(
                    "The active subscription does not contain a supported plan price.",
                    reason_code="billing_price_missing",
                )
            _require_pending_plan_match_if_correlated(
                organization,
                obj=obj,
                plan_code=plan_code,
            )
            _materialize_webhook_plan(
                db,
                organization=organization,
                plan_code=plan_code,
            )
        elif status in ACCESS_ENDING_STATUSES:
            _materialize_webhook_plan(
                db,
                organization=organization,
                plan_code="solo",
            )
        organization.billing_subscription_status = status
        organization.billing_subscription_event_created_at = event_created
        organization.billing_subscription_event_type = event_type
        organization.billing_last_event_created_at = event_created
        _confirm_checkout_from_subscription(organization, obj=obj, plan_code=organization.plan_type)
        _refresh_derived_billing_state(organization)
    elif event_type in {
        "invoice.payment_failed",
        "invoice.payment_action_required",
        "invoice.paid",
    }:
        if not _should_apply_payment_event(
            organization,
            event_type=event_type,
            event_created=event_created,
        ):
            return "older_or_lower_priority_payment_event"
        organization.billing_payment_status = _payment_status_for_event(event_type)
        organization.billing_payment_event_created_at = event_created
        organization.billing_payment_event_type = event_type
        _refresh_derived_billing_state(organization)
    else:
        return "unsupported_billing_event_type"
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
    return None


def _materialize_webhook_plan(
    db: Session,
    *,
    organization: Organization,
    plan_code: str,
) -> None:
    # A fully closed organization remains inaccessible and immutable, but its
    # signed billing facts can still be recorded by the caller. Do not recreate
    # commercial state after closure.
    if organization.status.strip().lower() == "closed":
        return
    try:
        apply_commercial_plan(
            db,
            organization_id=organization.id,
            plan_code=plan_code,
            system_billing_transition=True,
        )
    except CostEconomicsError as exc:
        raise BillingError(
            "The billing plan could not be applied safely.",
            reason_code=exc.reason_code,
            status_code=503,
        ) from exc


def _resolve_organization_for_event(
    db: Session,
    *,
    obj: dict[str, Any],
) -> Organization | None:
    metadata = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
    metadata_org_id = str(metadata.get("organization_id") or "").strip()
    reference_org_id = str(obj.get("client_reference_id") or "").strip()
    if metadata_org_id and reference_org_id and metadata_org_id != reference_org_id:
        raise BillingError(
            "The billing event organization identifiers do not agree.",
            reason_code="billing_organization_mismatch",
        )
    organization = db.get(Organization, metadata_org_id or reference_org_id) if (metadata_org_id or reference_org_id) else None
    customer_id = _provider_object_id(obj.get("customer"))
    subscription_id = _event_subscription_id(
        obj,
        require_invoice_consistency=False,
    )
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
    return organization


def _validate_event_against_locked_organization(
    organization: Organization,
    *,
    event_type: str,
    obj: dict[str, Any],
) -> None:
    customer_id = _provider_object_id(obj.get("customer"))
    subscription_id = _event_subscription_id(
        obj,
        require_invoice_consistency=True,
    )
    if customer_id and organization.stripe_customer_id not in {None, customer_id}:
        raise BillingError(
            "The billing customer does not match this organization.",
            reason_code="billing_customer_mismatch",
        )
    if event_type.startswith("invoice."):
        _require_current_invoice_subscription(
            organization,
            subscription_id=subscription_id,
        )
        return
    if (
        subscription_id
        and organization.stripe_subscription_id not in {None, subscription_id}
        and event_type not in ({"checkout.session.completed"} | AUTHORITATIVE_STATE_EVENT_TYPES)
    ):
        raise BillingError(
            "The billing subscription does not match this organization.",
            reason_code="billing_subscription_mismatch",
        )


def _require_current_invoice_subscription(
    organization: Organization,
    *,
    subscription_id: str,
) -> None:
    if not subscription_id:
        raise BillingError(
            "This invoice is not connected to the organization's current subscription.",
            reason_code="billing_invoice_subscription_missing",
        )
    if (
        not organization.stripe_subscription_id
        or subscription_id != organization.stripe_subscription_id
    ):
        raise BillingError(
            "This invoice does not match the organization's current subscription.",
            reason_code="billing_invoice_subscription_mismatch",
        )


def _event_subscription_id(
    obj: dict[str, Any],
    *,
    require_invoice_consistency: bool,
) -> str:
    object_type = str(obj.get("object") or "").strip()
    if object_type == "invoice":
        return _invoice_subscription_id(
            obj,
            require_consistency=require_invoice_consistency,
        )
    if object_type == "subscription":
        return _provider_object_id(obj.get("id"))
    return _provider_object_id(obj.get("subscription"))


def _invoice_subscription_id(
    obj: dict[str, Any],
    *,
    require_consistency: bool,
) -> str:
    legacy_subscription_id = _provider_object_id(obj.get("subscription"))
    raw_parent = obj.get("parent")
    if raw_parent:
        parent = raw_parent if isinstance(raw_parent, dict) else {}
        if str(parent.get("type") or "").strip() != "subscription_details":
            if require_consistency and legacy_subscription_id:
                raise BillingError(
                    "The invoice contains conflicting subscription references.",
                    reason_code="billing_invoice_subscription_conflict",
                )
            return ""
        details = (
            parent.get("subscription_details")
            if isinstance(parent.get("subscription_details"), dict)
            else {}
        )
        current_subscription_id = _provider_object_id(details.get("subscription"))
        if not current_subscription_id:
            return ""
        if (
            require_consistency
            and legacy_subscription_id
            and legacy_subscription_id != current_subscription_id
        ):
            raise BillingError(
                "The invoice contains conflicting subscription references.",
                reason_code="billing_invoice_subscription_conflict",
            )
        return current_subscription_id
    # Top-level subscription is used only for pre-Basil events without a parent.
    return legacy_subscription_id


def _provider_object_id(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("id")
    return str(value or "").strip()


def _lock_organization(db: Session, organization_id: str) -> Organization:
    organization = (
        db.query(Organization)
        .filter(Organization.id == organization_id)
        .populate_existing()
        .with_for_update()
        .one_or_none()
    )
    if organization is None:
        raise BillingError(
            "Organization not found.",
            reason_code="organization_not_found",
            status_code=404,
        )
    return organization


def _pending_checkout_is_active(
    organization: Organization,
    *,
    now: datetime,
) -> bool:
    expires_at = organization.billing_pending_checkout_expires_at
    return bool(
        organization.billing_pending_checkout_request_id
        and organization.billing_pending_checkout_session_id
        and organization.billing_pending_checkout_plan_code
        and expires_at
        and _as_utc(expires_at) > now
    )


def _clear_pending_checkout(organization: Organization) -> None:
    organization.billing_pending_checkout_request_id = None
    organization.billing_pending_checkout_session_id = None
    organization.billing_pending_checkout_plan_code = None
    organization.billing_pending_checkout_expires_at = None


def _event_checkout_request_id(obj: dict[str, Any]) -> str | None:
    metadata = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
    value = str(metadata.get("client_request_id") or "").strip()
    return _validate_checkout_request_id(value) if value else None


def _confirm_checkout(organization: Organization, *, obj: dict[str, Any]) -> None:
    request_id = _event_checkout_request_id(obj)
    session_id = str(obj.get("id") or "").strip()
    metadata = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
    requested_plan_value = str(metadata.get("requested_plan_code") or "").strip()
    requested_plan = (
        resolve_plan_economics(requested_plan_value).code if requested_plan_value else None
    )
    if not request_id or not session_id or not requested_plan:
        raise BillingError(
            "The completed checkout is missing its saved correlation details.",
            reason_code="checkout_correlation_missing",
        )
    if request_id == organization.billing_pending_checkout_request_id:
        if (
            session_id != organization.billing_pending_checkout_session_id
            or requested_plan != organization.billing_pending_checkout_plan_code
        ):
            raise BillingError(
                "The completed checkout does not match the saved pending checkout.",
                reason_code="checkout_correlation_mismatch",
            )
        _promote_pending_checkout_to_confirmed(organization)
        return
    if request_id == organization.billing_last_checkout_request_id:
        if (
            session_id != organization.billing_last_checkout_session_id
            or requested_plan != organization.billing_last_checkout_plan_code
        ):
            raise BillingError(
                "The completed checkout does not match the saved confirmation.",
                reason_code="checkout_correlation_mismatch",
            )
        return
    raise BillingError(
        "The completed checkout does not match a checkout started by this organization.",
        reason_code="checkout_correlation_mismatch",
    )


def _confirm_checkout_from_subscription(
    organization: Organization,
    *,
    obj: dict[str, Any],
    plan_code: str,
) -> None:
    request_id = _event_checkout_request_id(obj)
    if not request_id:
        return
    if request_id == organization.billing_pending_checkout_request_id:
        if plan_code != organization.billing_pending_checkout_plan_code:
            raise BillingError(
                "The subscription plan does not match the saved pending checkout.",
                reason_code="checkout_plan_mismatch",
            )
        _promote_pending_checkout_to_confirmed(organization)
        return
    if request_id == organization.billing_last_checkout_request_id:
        return
    if organization.billing_pending_checkout_request_id:
        raise BillingError(
            "The subscription does not match the saved pending checkout.",
            reason_code="checkout_correlation_mismatch",
        )


def _promote_pending_checkout_to_confirmed(organization: Organization) -> None:
    organization.billing_last_checkout_request_id = (
        organization.billing_pending_checkout_request_id
    )
    organization.billing_last_checkout_session_id = (
        organization.billing_pending_checkout_session_id
    )
    organization.billing_last_checkout_plan_code = organization.billing_pending_checkout_plan_code
    _clear_pending_checkout(organization)


def _require_pending_plan_match_if_correlated(
    organization: Organization,
    *,
    obj: dict[str, Any],
    plan_code: str,
) -> None:
    request_id = _event_checkout_request_id(obj)
    if (
        request_id
        and request_id == organization.billing_pending_checkout_request_id
        and plan_code != organization.billing_pending_checkout_plan_code
    ):
        raise BillingError(
            "The subscription price does not match the saved pending checkout.",
            reason_code="checkout_plan_mismatch",
        )


def _require_created_subscription_plan_match(
    obj: dict[str, Any],
    *,
    price_plan_code: str,
) -> None:
    metadata = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
    raw_plan_code = str(metadata.get("plan_code") or "").strip()
    if not raw_plan_code:
        raise BillingError(
            "The new subscription is missing its signed plan details.",
            reason_code="billing_plan_metadata_missing",
        )
    try:
        metadata_plan_code = resolve_plan_economics(raw_plan_code).code
    except CostEconomicsError as exc:
        raise BillingError(
            "The new subscription contains unsupported signed plan details.",
            reason_code="billing_plan_metadata_invalid",
        ) from exc
    if metadata_plan_code != price_plan_code:
        raise BillingError(
            "The new subscription plan does not match its configured price.",
            reason_code="billing_plan_price_mismatch",
        )


def _assign_subscription_id(
    db: Session,
    *,
    organization: Organization,
    event_type: str,
    obj: dict[str, Any],
    value: Any,
) -> bool:
    normalized = str(value or "").strip()
    if not normalized:
        return False
    current = organization.stripe_subscription_id
    if not current:
        organization.stripe_subscription_id = normalized
        return False
    if current == normalized:
        return False
    request_id = _event_checkout_request_id(obj)
    if _current_subscription_status(organization) not in ACCESS_ENDING_STATUSES:
        raise BillingError(
            "The existing subscription must end before a replacement can be connected.",
            reason_code="billing_subscription_rotation_not_terminal",
        )
    if not request_id or request_id != organization.billing_pending_checkout_request_id:
        raise BillingError(
            "The replacement subscription does not match the saved pending checkout.",
            reason_code="billing_subscription_rotation_not_authorized",
        )
    previous = current
    organization.stripe_subscription_id = normalized
    organization.stripe_price_id = None
    organization.billing_cancel_at_period_end = False
    organization.billing_current_period_end = None
    organization.billing_subscription_status = None
    organization.billing_subscription_event_created_at = None
    organization.billing_subscription_event_type = None
    organization.billing_last_event_created_at = None
    organization.billing_payment_status = None
    organization.billing_payment_event_created_at = None
    organization.billing_payment_event_type = None
    organization.billing_status = None
    organization.billing_last_error_code = None
    write_audit_log(
        db,
        tenant_id=organization.id,
        actor_user_id=None,
        event_type="billing.subscription.rotated",
        payload={
            "organization_id": organization.id,
            "provider_event_type": event_type,
            "client_request_id": request_id,
            "previous_subscription_id": previous,
            "new_subscription_id": normalized,
        },
    )
    return True


def _current_subscription_status(organization: Organization) -> str | None:
    if organization.billing_subscription_status:
        return organization.billing_subscription_status
    legacy = str(organization.billing_status or "").strip()
    return legacy if legacy in (ACTIVE_STATUSES | ACCESS_ENDING_STATUSES) else None


def _should_apply_subscription_event(
    organization: Organization,
    *,
    event_type: str,
    event_created: datetime,
    incoming_status: str,
    incoming_plan_code: str | None,
    rotated: bool,
) -> bool:
    if rotated:
        return True
    saved_status = _current_subscription_status(organization)
    if saved_status in ACCESS_ENDING_STATUSES and incoming_status not in ACCESS_ENDING_STATUSES:
        return False
    saved_created = organization.billing_subscription_event_created_at
    if saved_created is None:
        return True
    saved_created = _as_utc(saved_created)
    if event_created > saved_created:
        return True
    if event_created < saved_created:
        return False
    incoming_key = (_subscription_event_priority(event_type, incoming_status), event_type)
    saved_type = organization.billing_subscription_event_type or "legacy.migrated"
    saved_key = (_subscription_event_priority(saved_type, saved_status or ""), saved_type)
    if incoming_key == saved_key and event_type == "customer.subscription.updated":
        return _same_second_subscription_update_is_conservative(
            organization,
            incoming_status=incoming_status,
            incoming_plan_code=incoming_plan_code,
        )
    return incoming_key > saved_key


def _same_second_subscription_update_is_conservative(
    organization: Organization,
    *,
    incoming_status: str,
    incoming_plan_code: str | None,
) -> bool:
    saved_status = _current_subscription_status(organization)
    if saved_status != incoming_status:
        return False
    if incoming_status not in ACTIVE_STATUSES or incoming_plan_code is None:
        return False
    saved_plan_code = resolve_plan_economics(organization.plan_type).code
    if incoming_plan_code == saved_plan_code:
        return False
    # Stripe event timestamps have only second precision. Two different active plan
    # updates in the same second have no canonical provider ordering, so deterministically
    # retain the lower entitlement until a later event disambiguates the state.
    return _plan_entitlement_rank(incoming_plan_code) < _plan_entitlement_rank(
        saved_plan_code
    )


def _plan_entitlement_rank(plan_code: str) -> int:
    return {
        "solo": 0,
        "multi_location": 1,
        "enterprise": 2,
    }[plan_code]


def _subscription_event_priority(event_type: str, status: str) -> int:
    if event_type == "customer.subscription.deleted":
        return 400
    if status in ACCESS_ENDING_STATUSES:
        return 300
    if event_type == "customer.subscription.updated":
        return 200
    if event_type == "customer.subscription.created":
        return 100
    return 0


def _should_apply_payment_event(
    organization: Organization,
    *,
    event_type: str,
    event_created: datetime,
) -> bool:
    saved_created = organization.billing_payment_event_created_at
    if saved_created is None:
        return True
    saved_created = _as_utc(saved_created)
    if event_created > saved_created:
        return True
    if event_created < saved_created:
        return False
    saved_type = organization.billing_payment_event_type or "legacy.migrated"
    return (_payment_event_priority(event_type), event_type) > (
        _payment_event_priority(saved_type),
        saved_type,
    )


def _payment_event_priority(event_type: str) -> int:
    return {
        "invoice.paid": 100,
        "invoice.payment_action_required": 200,
        "invoice.payment_failed": 300,
    }.get(event_type, 0)


def _payment_status_for_event(event_type: str) -> str:
    return {
        "invoice.paid": "paid",
        "invoice.payment_action_required": "payment_action_required",
        "invoice.payment_failed": "past_due",
    }[event_type]


def _refresh_derived_billing_state(organization: Organization) -> None:
    subscription_status = _current_subscription_status(organization)
    payment_status = organization.billing_payment_status
    if subscription_status in ACCESS_ENDING_STATUSES:
        status = subscription_status
    elif payment_status in {"past_due", "payment_action_required"}:
        status = payment_status
    elif subscription_status in ACTIVE_STATUSES:
        status = subscription_status
    elif organization.billing_last_checkout_request_id:
        status = "checkout_completed"
    else:
        status = subscription_status or "not_started"
    organization.billing_status = status
    if status in ACCESS_ENDING_STATUSES:
        organization.billing_last_error_code = "subscription_ended"
    elif status == "past_due":
        organization.billing_last_error_code = "payment_failed"
    elif status == "payment_action_required":
        organization.billing_last_error_code = "payment_action_required"
    else:
        organization.billing_last_error_code = None


def _plan_for_subscription(price_id: str | None) -> str:
    if not price_id:
        raise BillingError(
            "The subscription does not contain a supported plan price.",
            reason_code="billing_price_missing",
        )
    return _plan_code_for_price(price_id)


def _subscription_price_id(obj: dict[str, Any]) -> str | None:
    items = obj.get("items", {}).get("data", [])
    if not isinstance(items, list) or not items:
        return None
    price = items[0].get("price", {}) if isinstance(items[0], dict) else {}
    return str(price.get("id") or "").strip() or None


def _subscription_current_period_end(obj: dict[str, Any]) -> datetime | None:
    items = obj.get("items", {}).get("data", [])
    item_periods: list[datetime] = []
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            period = _safe_optional_event_datetime(item.get("current_period_end"))
            if period is not None:
                item_periods.append(period)
    if item_periods:
        # Stripe ends mixed-interval subscriptions at the earliest item period. This
        # catalog has one item, while min() remains deterministic and conservative.
        return min(item_periods)
    return _safe_optional_event_datetime(obj.get("current_period_end"))


def _safe_optional_event_datetime(value: Any) -> datetime | None:
    if isinstance(value, bool):
        return None
    try:
        return _optional_event_datetime(value)
    except (BillingError, TypeError):
        return None


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


def _validate_checkout_request_id(value: str) -> str:
    normalized = str(value or "").strip()
    if not CHECKOUT_REQUEST_ID_PATTERN.fullmatch(normalized):
        raise BillingError(
            "The checkout request identifier is invalid.",
            reason_code="checkout_request_id_invalid",
            status_code=422,
        )
    return normalized


def _checkout_idempotency_key(
    *,
    organization_id: str,
    plan_code: str,
    client_request_id: str,
) -> str:
    stable_scope = json.dumps(
        [organization_id, plan_code, client_request_id],
        separators=(",", ":"),
    )
    digest = hashlib.sha256(stable_scope.encode("utf-8")).hexdigest()
    return f"insightos-checkout-{digest}"


def _require_matching_webhook_payload(
    receipt: BillingWebhookEvent,
    payload_sha256: str,
) -> None:
    if not hmac.compare_digest(receipt.payload_sha256, payload_sha256):
        raise BillingError(
            "The billing event identifier was reused with a different payload.",
            reason_code="billing_event_payload_conflict",
            status_code=409,
        )


def _checkout_confirmation(organization: Organization) -> dict[str, Any]:
    status = organization.billing_status or "not_started"
    requested_plan = organization.billing_last_checkout_plan_code
    current_plan = resolve_plan_economics(organization.plan_type).code
    request_id = organization.billing_last_checkout_request_id
    return {
        "client_request_id": request_id,
        "session_id": organization.billing_last_checkout_session_id,
        "requested_plan_code": requested_plan,
        "checkout_completed": bool(request_id and status != "not_started"),
        "subscription_active": bool(
            request_id
            and requested_plan
            and status in ACTIVE_STATUSES
            and current_plan == requested_plan
        ),
    }


def _pending_checkout_summary(organization: Organization) -> dict[str, Any]:
    expires_at = organization.billing_pending_checkout_expires_at
    return {
        "client_request_id": organization.billing_pending_checkout_request_id,
        "session_id": organization.billing_pending_checkout_session_id,
        "requested_plan_code": organization.billing_pending_checkout_plan_code,
        "expires_at": _iso(expires_at),
        "active": _pending_checkout_is_active(organization, now=datetime.now(UTC)),
    }


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
