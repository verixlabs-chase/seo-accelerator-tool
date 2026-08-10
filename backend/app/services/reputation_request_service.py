from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
import hashlib
import re
from typing import Any
from urllib.parse import urlparse

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.business_location import BusinessLocation
from app.models.campaign import Campaign
from app.models.data_connection import DataConnection
from app.models.google_business_profile import GoogleBusinessProfileSnapshot
from app.models.reputation import (
    ReputationReview,
    ReputationReviewRequestCampaign,
    ReputationReviewRequestDelivery,
    ReputationReviewRequestRecipient,
    ReputationReviewRequestSuppression,
)
from app.providers.email import SyntheticEmailAdapter, get_email_adapter
from app.services import infra_service


CONSENT_POLICY_VERSION = "review-request-consent-v1"
SUPPRESSION_POLICY_VERSION = "review-request-suppression-v1"
GOOGLE_PROFILE_PROVIDER = "google_business_profile"
PASSIVE_CHANNELS = {"link", "qr", "kiosk"}
SUPPORTED_CHANNELS = PASSIVE_CHANNELS | {"email", "sms"}
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PROHIBITED_GATING_PHRASES = (
    "if you had a good experience",
    "if you were happy",
    "if you're happy",
    "if you are happy",
    "leave a positive review",
    "leave us a 5 star",
    "leave us a five star",
    "five-star review",
    "5-star review",
)
ALLOWED_REVIEW_HOSTS = {
    "g.page",
    "maps.app.goo.gl",
    "search.google.com",
}


def _now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _campaign_context(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
) -> tuple[Campaign, BusinessLocation]:
    campaign = (
        db.query(Campaign)
        .filter(
            Campaign.id == campaign_id,
            Campaign.tenant_id == tenant_id,
            Campaign.organization_id == organization_id,
        )
        .first()
    )
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    location = db.get(BusinessLocation, campaign.business_location_id)
    if location is None or location.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Choose a business location before creating a review request.",
        )
    return campaign, location


def _request_campaign(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    request_campaign_id: str,
) -> ReputationReviewRequestCampaign:
    row = (
        db.query(ReputationReviewRequestCampaign)
        .filter(
            ReputationReviewRequestCampaign.id == request_campaign_id,
            ReputationReviewRequestCampaign.tenant_id == tenant_id,
            ReputationReviewRequestCampaign.organization_id == organization_id,
        )
        .first()
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review request campaign not found",
        )
    return row


def _review_count(db: Session, campaign_id: str) -> int:
    return (
        db.query(ReputationReview)
        .filter(
            ReputationReview.campaign_id == campaign_id,
            ReputationReview.source_type == "owned_profile",
        )
        .count()
    )


def _google_review_url(value: str) -> str:
    normalized = str(value or "").strip()
    parsed = urlparse(normalized)
    hostname = (parsed.hostname or "").lower()
    allowed = (
        hostname in ALLOWED_REVIEW_HOSTS
        or hostname.endswith(".g.page")
        or hostname == "google.com"
        or hostname.endswith(".google.com")
    )
    if parsed.scheme != "https" or not allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use the secure Google review link for this business location.",
        )
    return normalized


def _connected_review_url(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
) -> str | None:
    connection = (
        db.query(DataConnection)
        .filter(
            DataConnection.tenant_id == tenant_id,
            DataConnection.organization_id == organization_id,
            DataConnection.campaign_id == campaign_id,
            DataConnection.provider_name == GOOGLE_PROFILE_PROVIDER,
            DataConnection.status != "disconnected",
        )
        .first()
    )
    if connection is None:
        return None
    latest = (
        db.query(GoogleBusinessProfileSnapshot)
        .filter(GoogleBusinessProfileSnapshot.connection_id == connection.id)
        .order_by(GoogleBusinessProfileSnapshot.captured_at.desc())
        .first()
    )
    profile = dict(latest.profile_data or {}) if latest is not None else {}
    metadata = profile.get("metadata") if isinstance(profile.get("metadata"), dict) else {}
    connection_metadata = dict(connection.connection_metadata or {})
    candidates = (
        metadata.get("newReviewUri"),
        metadata.get("new_review_uri"),
        connection_metadata.get("newReviewUri"),
        connection_metadata.get("new_review_uri"),
        connection_metadata.get("review_url"),
    )
    for candidate in candidates:
        if not candidate:
            continue
        try:
            return _google_review_url(str(candidate))
        except HTTPException:
            continue
    return None


def _safe_message(value: str, *, review_url: str, location_name: str) -> str:
    normalized = " ".join(str(value or "").strip().split())
    if not normalized:
        normalized = (
            f"Thank you for choosing {location_name}. Would you share an honest review? "
            "Your feedback helps us improve."
        )
    lowered = normalized.lower()
    if any(phrase in lowered for phrase in PROHIBITED_GATING_PHRASES):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Ask every eligible customer for an honest review. Do not request only positive "
                "or five-star feedback."
            ),
        )
    if len(normalized) > 700:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Keep the review request under 700 characters.",
        )
    if review_url not in normalized:
        normalized = f"{normalized} {review_url}"
    return normalized


def _contact_hash(value: str) -> str:
    return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()


def _email(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if len(normalized) > 320 or not EMAIL_PATTERN.fullmatch(normalized):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Enter a valid customer email address.",
        )
    return normalized


def _masked_email(value: str) -> str:
    local, domain = value.split("@", 1)
    visible = local[:1] if local else ""
    return f"{visible}{'*' * max(3, len(local) - 1)}@{domain}"


def delivery_readiness() -> dict[str, Any]:
    adapter = get_email_adapter()
    live_email_adapter = not isinstance(adapter, SyntheticEmailAdapter)
    email_available = bool(infra_service.smtp_configured() and live_email_adapter)
    return {
        "channels": {
            "link": {
                "available": True,
                "label": "Share a review link",
                "reason": "Copy the same honest-review link for any eligible customer.",
            },
            "qr": {
                "available": True,
                "label": "Use the review link in a QR code",
                "reason": "The saved link is ready for a QR code. Image export is not included yet.",
            },
            "kiosk": {
                "available": True,
                "label": "Open the review link at checkout",
                "reason": "The same page is shown to every eligible customer without rating questions.",
            },
            "email": {
                "available": email_available,
                "label": "Send by email",
                "reason": (
                    "A verified live email provider is connected."
                    if email_available
                    else "Connect a verified transactional email provider before sending customer requests."
                ),
            },
            "sms": {
                "available": False,
                "label": "Send by text message",
                "reason": "SMS needs its own provider, written consent rules, price card, and delivery receipts.",
            },
        },
        "review_gating_allowed": False,
        "automatic_satisfaction_filtering_allowed": False,
        "consent_policy_version": CONSENT_POLICY_VERSION,
        "suppression_policy_version": SUPPRESSION_POLICY_VERSION,
    }


def create_campaign(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
    user_id: str,
    name: str,
    channel: str,
    subject: str | None,
    message_body: str,
    review_url: str | None,
) -> dict[str, Any]:
    campaign, location = _campaign_context(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
    )
    normalized_channel = str(channel or "").strip().lower()
    if normalized_channel not in SUPPORTED_CHANNELS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Choose a supported request type.")
    if normalized_channel == "sms":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=delivery_readiness()["channels"]["sms"]["reason"],
        )
    connected_url = _connected_review_url(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
    )
    resolved_url = connected_url or (_google_review_url(review_url) if review_url else None)
    if not resolved_url:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "The connected business listing did not provide its review link. Paste the location's "
                "secure Google review link to continue."
            ),
        )
    resolved_now = _now()
    campaign_name = str(name or "").strip() or f"{location.name} review requests"
    if len(campaign_name) > 160:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Campaign name is too long.")
    resolved_subject = str(subject or "").strip() or f"How did we do at {location.name}?"
    if len(resolved_subject) > 180:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email subject is too long.")
    row = ReputationReviewRequestCampaign(
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign.id,
        business_location_id=location.id,
        name=campaign_name,
        channel=normalized_channel,
        status="active" if normalized_channel in PASSIVE_CHANNELS else "draft",
        subject=resolved_subject if normalized_channel == "email" else None,
        message_body=_safe_message(
            message_body,
            review_url=resolved_url,
            location_name=location.name,
        ),
        review_url=resolved_url,
        review_url_source="connected_profile" if connected_url else "owner_provided",
        audience_rule={
            "eligibility": "all_confirmed_eligible_customers",
            "service_completion_required": True,
            "rating_or_satisfaction_filter_allowed": False,
        },
        consent_policy_version=CONSENT_POLICY_VERSION,
        suppression_policy_version=SUPPRESSION_POLICY_VERSION,
        baseline_review_count=_review_count(db, campaign.id),
        baseline_at=resolved_now,
        created_by_user_id=user_id,
        started_at=resolved_now if normalized_channel in PASSIVE_CHANNELS else None,
        paused_at=None,
        completed_at=None,
        created_at=resolved_now,
        updated_at=resolved_now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return serialize_campaign(db, row)


def list_campaigns(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
) -> list[dict[str, Any]]:
    _campaign_context(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
    )
    rows = (
        db.query(ReputationReviewRequestCampaign)
        .filter(
            ReputationReviewRequestCampaign.tenant_id == tenant_id,
            ReputationReviewRequestCampaign.organization_id == organization_id,
            ReputationReviewRequestCampaign.campaign_id == campaign_id,
        )
        .order_by(ReputationReviewRequestCampaign.created_at.desc())
        .all()
    )
    return [serialize_campaign(db, row) for row in rows]


def add_recipient(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    request_campaign_id: str,
    email_address: str,
    customer_name: str | None,
    consent_basis: str,
    consent_source: str,
    consent_confirmed: bool,
    service_completed_at: datetime,
) -> dict[str, Any]:
    row = _request_campaign(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        request_campaign_id=request_campaign_id,
    )
    if row.channel != "email":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Customer email recipients belong only to an email request campaign.",
        )
    if row.status not in {"draft", "paused"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Pause this campaign before changing its customer list.",
        )
    if not consent_confirmed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirm that this customer can receive this review request.",
        )
    if consent_basis not in {
        "explicit_opt_in",
        "existing_customer_relationship",
        "customer_requested",
    }:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Choose a valid consent basis.")
    completed_at = _as_utc(service_completed_at)
    resolved_now = _now()
    if completed_at > resolved_now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The service completion time cannot be in the future.",
        )
    normalized_email = _email(email_address)
    contact_hash = _contact_hash(normalized_email)
    existing = (
        db.query(ReputationReviewRequestRecipient)
        .filter(
            ReputationReviewRequestRecipient.request_campaign_id == row.id,
            ReputationReviewRequestRecipient.contact_hash == contact_hash,
        )
        .first()
    )
    if existing is not None:
        return serialize_recipient(existing)
    suppression = (
        db.query(ReputationReviewRequestSuppression)
        .filter(
            ReputationReviewRequestSuppression.organization_id == organization_id,
            ReputationReviewRequestSuppression.channel == "email",
            ReputationReviewRequestSuppression.contact_hash == contact_hash,
        )
        .first()
    )
    recipient = ReputationReviewRequestRecipient(
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=row.campaign_id,
        business_location_id=row.business_location_id,
        request_campaign_id=row.id,
        email_address=normalized_email,
        contact_hash=contact_hash,
        customer_name=str(customer_name or "").strip() or None,
        consent_basis=consent_basis,
        consent_source=str(consent_source or "").strip() or "Confirmed by account owner",
        consent_confirmed_at=resolved_now,
        service_completed_at=completed_at,
        status="suppressed" if suppression is not None else "eligible",
        suppression_reason=suppression.reason if suppression is not None else None,
        suppressed_at=resolved_now if suppression is not None else None,
        created_at=resolved_now,
        updated_at=resolved_now,
    )
    db.add(recipient)
    db.commit()
    db.refresh(recipient)
    return serialize_recipient(recipient)


def suppress_recipient(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    recipient_id: str,
    reason: str,
    source: str,
) -> dict[str, Any]:
    recipient = (
        db.query(ReputationReviewRequestRecipient)
        .filter(
            ReputationReviewRequestRecipient.id == recipient_id,
            ReputationReviewRequestRecipient.tenant_id == tenant_id,
            ReputationReviewRequestRecipient.organization_id == organization_id,
        )
        .first()
    )
    if recipient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer request record not found")
    resolved_now = _now()
    suppression = (
        db.query(ReputationReviewRequestSuppression)
        .filter(
            ReputationReviewRequestSuppression.organization_id == organization_id,
            ReputationReviewRequestSuppression.channel == "email",
            ReputationReviewRequestSuppression.contact_hash == recipient.contact_hash,
        )
        .first()
    )
    if suppression is None:
        suppression = ReputationReviewRequestSuppression(
            tenant_id=tenant_id,
            organization_id=organization_id,
            channel="email",
            contact_hash=recipient.contact_hash,
            reason=str(reason or "").strip() or "Do not send review requests",
            source=str(source or "").strip() or "Account owner",
            created_at=resolved_now,
        )
        db.add(suppression)
    recipients = (
        db.query(ReputationReviewRequestRecipient)
        .filter(
            ReputationReviewRequestRecipient.organization_id == organization_id,
            ReputationReviewRequestRecipient.contact_hash == recipient.contact_hash,
        )
        .all()
    )
    for item in recipients:
        item.status = "suppressed"
        item.suppression_reason = suppression.reason
        item.suppressed_at = resolved_now
        item.updated_at = resolved_now
    db.commit()
    db.refresh(recipient)
    return serialize_recipient(recipient)


def control_campaign(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    request_campaign_id: str,
    action: str,
) -> dict[str, Any]:
    row = _request_campaign(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        request_campaign_id=request_campaign_id,
    )
    normalized_action = str(action or "").strip().lower()
    resolved_now = _now()
    if normalized_action == "activate":
        readiness = delivery_readiness()["channels"][row.channel]
        if not readiness["available"]:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=readiness["reason"])
        if row.channel == "email":
            eligible = (
                db.query(ReputationReviewRequestRecipient)
                .filter(
                    ReputationReviewRequestRecipient.request_campaign_id == row.id,
                    ReputationReviewRequestRecipient.status == "eligible",
                )
                .count()
            )
            if eligible == 0:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Add at least one consent-confirmed customer who is not suppressed.",
                )
        row.status = "active"
        row.started_at = row.started_at or resolved_now
        row.paused_at = None
    elif normalized_action == "pause" and row.status == "active":
        row.status = "paused"
        row.paused_at = resolved_now
    elif normalized_action == "complete" and row.status in {"active", "paused"}:
        row.status = "completed"
        row.completed_at = resolved_now
    elif normalized_action == "cancel" and row.status in {"draft", "active", "paused"}:
        row.status = "cancelled"
        row.completed_at = resolved_now
    else:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That campaign change is not available from its current state.",
        )
    row.updated_at = resolved_now
    db.commit()
    db.refresh(row)
    return serialize_campaign(db, row)


def serialize_recipient(row: ReputationReviewRequestRecipient) -> dict[str, Any]:
    return {
        "id": row.id,
        "request_campaign_id": row.request_campaign_id,
        "email": _masked_email(row.email_address),
        "customer_name": row.customer_name,
        "consent_basis": row.consent_basis,
        "consent_source": row.consent_source,
        "consent_confirmed_at": row.consent_confirmed_at.isoformat(),
        "service_completed_at": row.service_completed_at.isoformat(),
        "status": row.status,
        "suppression_reason": row.suppression_reason,
        "created_at": row.created_at.isoformat(),
    }


def serialize_campaign(db: Session, row: ReputationReviewRequestCampaign) -> dict[str, Any]:
    recipients = (
        db.query(ReputationReviewRequestRecipient)
        .filter(ReputationReviewRequestRecipient.request_campaign_id == row.id)
        .order_by(ReputationReviewRequestRecipient.created_at.desc())
        .all()
    )
    deliveries = (
        db.query(ReputationReviewRequestDelivery)
        .filter(ReputationReviewRequestDelivery.request_campaign_id == row.id)
        .all()
    )
    recipient_counts = Counter(item.status for item in recipients)
    delivery_counts = Counter(item.status for item in deliveries)
    current_review_count = _review_count(db, row.campaign_id)
    reviews_since_start = max(0, current_review_count - int(row.baseline_review_count or 0))
    return {
        "id": row.id,
        "campaign_id": row.campaign_id,
        "business_location_id": row.business_location_id,
        "name": row.name,
        "channel": row.channel,
        "status": row.status,
        "subject": row.subject,
        "message_body": row.message_body,
        "review_url": row.review_url,
        "review_url_source": row.review_url_source,
        "share_url": row.review_url,
        "audience_rule": dict(row.audience_rule or {}),
        "consent_policy_version": row.consent_policy_version,
        "suppression_policy_version": row.suppression_policy_version,
        "recipients": [serialize_recipient(item) for item in recipients],
        "recipient_summary": {
            "total": len(recipients),
            "eligible": recipient_counts["eligible"],
            "suppressed": recipient_counts["suppressed"],
            "sent": recipient_counts["sent"] + recipient_counts["delivered"],
        },
        "delivery_summary": dict(delivery_counts),
        "result_summary": {
            "baseline_review_count": row.baseline_review_count,
            "current_review_count": current_review_count,
            "new_reviews_since_start": reviews_since_start,
            "attribution_state": "time_window_only",
            "note": (
                "This shows new reviews after the campaign started. It does not claim the campaign caused them."
            ),
        },
        "created_at": row.created_at.isoformat(),
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "paused_at": row.paused_at.isoformat() if row.paused_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
    }
