from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.events import emit_event
from app.models.data_connection import DataConnection
from app.models.platform_job import PlatformJob
from app.models.reputation import (
    ReputationProviderCapability,
    ReputationResponseDraft,
    ReputationResponseExecution,
    ReputationReview,
)
from app.providers.google_reviews import (
    GoogleBusinessProfileReviewsProvider,
    GoogleReviewsProviderError,
)
from app.services import data_connections_service, job_service, reputation_inventory_service


PROVIDER_NAME = "google_business_profile"
CAPABILITY_NAME = "review_reply_update"
PROVIDER_METHOD = "accounts.locations.reviews.updateReply"
JOB_TYPE = "reputation.response.publish"
CONFIRMATION_VERSION = "review-reply-publish-consent-v1"
CONFIRMATION_LABEL = "I understand this approved reply will be published publicly on Google."
ACTIVE_CAPABILITY_STATUSES = {"validation_authorized", "verified"}
PAUSE_UNTIL = timedelta(days=3650)


def _now() -> datetime:
    return datetime.now(UTC)


def _digest(value: Any) -> str:
    return sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _customer_error(message: str, reason_code: str, http_status: int = 409) -> HTTPException:
    return HTTPException(
        status_code=http_status,
        detail={"message": message, "reason_code": reason_code},
    )


def _connection_for_campaign(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
) -> DataConnection | None:
    return (
        db.query(DataConnection)
        .filter(
            DataConnection.tenant_id == tenant_id,
            DataConnection.organization_id == organization_id,
            DataConnection.campaign_id == campaign_id,
            DataConnection.provider_name == PROVIDER_NAME,
            DataConnection.status != data_connections_service.CONNECTION_STATUS_DISCONNECTED,
        )
        .first()
    )


def _capability_for_connection(
    db: Session,
    connection_id: str,
) -> ReputationProviderCapability | None:
    return (
        db.query(ReputationProviderCapability)
        .filter(
            ReputationProviderCapability.connection_id == connection_id,
            ReputationProviderCapability.capability == CAPABILITY_NAME,
        )
        .first()
    )


def authorize_validation(
    db: Session,
    *,
    organization_id: str,
    connection_id: str,
    authorized_by_user_id: str,
    proof_reference: str,
) -> ReputationProviderCapability:
    connection = (
        db.query(DataConnection)
        .filter(
            DataConnection.id == connection_id,
            DataConnection.organization_id == organization_id,
            DataConnection.provider_name == PROVIDER_NAME,
            DataConnection.status != data_connections_service.CONNECTION_STATUS_DISCONNECTED,
        )
        .first()
    )
    if connection is None:
        raise _customer_error(
            "The connected Google business listing was not found.",
            "owned_profile_connection_required",
            404,
        )
    proof = proof_reference.strip()
    if len(proof) < 8:
        raise _customer_error(
            "Add the Google approval or support reference before authorizing validation.",
            "capability_proof_required",
            400,
        )
    now = _now()
    row = _capability_for_connection(db, connection.id)
    if row is None:
        row = ReputationProviderCapability(
            tenant_id=connection.tenant_id,
            organization_id=connection.organization_id,
            connection_id=connection.id,
            provider_name=PROVIDER_NAME,
            capability=CAPABILITY_NAME,
            provider_method=PROVIDER_METHOD,
            status="validation_authorized",
            proof_type="google_approval_reference",
            proof_reference=proof,
            authorized_by_user_id=authorized_by_user_id,
            authorized_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    else:
        row.status = "validation_authorized"
        row.proof_type = "google_approval_reference"
        row.proof_reference = proof
        row.authorized_by_user_id = authorized_by_user_id
        row.authorized_at = now
        row.revoked_at = None
        row.last_failure_code = None
        row.updated_at = now
    emit_event(
        db,
        tenant_id=connection.tenant_id,
        event_type="reputation.review_reply.capability.validation_authorized",
        payload={
            "organization_id": organization_id,
            "connection_id": connection.id,
            "capability": CAPABILITY_NAME,
            "provider_method": PROVIDER_METHOD,
        },
    )
    db.commit()
    db.refresh(row)
    return row


def revoke_capability(
    db: Session,
    *,
    organization_id: str,
    connection_id: str,
    revoked_by_user_id: str,
    reason: str,
) -> ReputationProviderCapability:
    row = _capability_for_connection(db, connection_id)
    if row is None or row.organization_id != organization_id:
        raise _customer_error("Review posting access was not found.", "capability_not_found", 404)
    now = _now()
    row.status = "revoked"
    row.revoked_at = now
    row.last_failure_at = now
    row.last_failure_code = reason.strip()[:120] or "manually_revoked"
    row.updated_at = now
    emit_event(
        db,
        tenant_id=row.tenant_id,
        event_type="reputation.review_reply.capability.revoked",
        payload={
            "organization_id": organization_id,
            "connection_id": connection_id,
            "revoked_by_user_id": revoked_by_user_id,
            "reason_code": row.last_failure_code,
        },
    )
    db.commit()
    db.refresh(row)
    return row


def serialize_capability(row: ReputationProviderCapability) -> dict[str, Any]:
    return {
        "id": row.id,
        "connection_id": row.connection_id,
        "provider_name": row.provider_name,
        "capability": row.capability,
        "provider_method": row.provider_method,
        "status": row.status,
        "proof_type": row.proof_type,
        "authorized_at": row.authorized_at.isoformat(),
        "verified_at": row.verified_at.isoformat() if row.verified_at else None,
        "last_success_at": row.last_success_at.isoformat() if row.last_success_at else None,
        "last_failure_at": row.last_failure_at.isoformat() if row.last_failure_at else None,
        "last_failure_code": row.last_failure_code,
    }


def posting_status(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
) -> dict[str, Any]:
    connection = _connection_for_campaign(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
    )
    capability = _capability_for_connection(db, connection.id) if connection else None
    available = capability is not None and capability.status in ACTIVE_CAPABILITY_STATUSES
    if connection is None:
        reason = "Connect this location to its Google business listing before posting replies."
        reason_code = "owned_profile_connection_required"
    elif capability is None:
        reason = "Review posting is waiting for verified Google access. You can still copy approved replies."
        reason_code = "review_reply_capability_not_authorized"
    elif capability.status == "revoked":
        reason = "Google review posting access needs attention. You can still copy approved replies."
        reason_code = capability.last_failure_code or "review_reply_capability_revoked"
    else:
        reason = "Approved replies can be posted after you confirm each one."
        reason_code = None
    return {
        "available": available,
        "automatic_posting_enabled": False,
        "explicit_confirmation_required": True,
        "confirmation_version": CONFIRMATION_VERSION,
        "confirmation_label": CONFIRMATION_LABEL,
        "connection_id": connection.id if connection else None,
        "capability_status": capability.status if capability else "not_authorized",
        "reason": reason,
        "reason_code": reason_code,
    }


def _review_resource_prefix(connection: DataConnection) -> str:
    metadata = dict(connection.connection_metadata or {})
    account_id = str(metadata.get("account_id") or "").strip().strip("/")
    location_id = str(connection.external_resource_id or "").strip().strip("/")
    if not account_id.startswith("accounts/") or not location_id.startswith("locations/"):
        return ""
    return f"{account_id}/{location_id}/reviews/"


def queue_execution(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
    draft_id: str,
    requested_by_user_id: str,
    confirmation_version: str,
    confirm_publish_to_google: bool,
) -> ReputationResponseExecution:
    if not confirm_publish_to_google or confirmation_version != CONFIRMATION_VERSION:
        raise _customer_error(
            "Confirm that this approved reply will be published publicly on Google.",
            "review_reply_publish_confirmation_required",
            400,
        )
    existing = (
        db.query(ReputationResponseExecution)
        .filter(
            ReputationResponseExecution.tenant_id == tenant_id,
            ReputationResponseExecution.organization_id == organization_id,
            ReputationResponseExecution.draft_id == draft_id,
        )
        .first()
    )
    if existing is not None:
        return existing

    draft = (
        db.query(ReputationResponseDraft)
        .filter(
            ReputationResponseDraft.id == draft_id,
            ReputationResponseDraft.tenant_id == tenant_id,
            ReputationResponseDraft.organization_id == organization_id,
            ReputationResponseDraft.campaign_id == campaign_id,
        )
        .first()
    )
    if draft is None:
        raise _customer_error("The approved reply was not found.", "review_reply_draft_not_found", 404)
    approved_text = str(draft.approved_text or "").strip()
    if (
        draft.status != "approved"
        or not approved_text
        or not draft.reviewed_by_user_id
        or draft.reviewed_at is None
    ):
        raise _customer_error(
            "Approve the reply wording before posting it.",
            "review_reply_approval_required",
        )
    review = db.get(ReputationReview, draft.review_id)
    if (
        review is None
        or review.tenant_id != tenant_id
        or review.organization_id != organization_id
        or review.campaign_id != campaign_id
        or review.source_type != "owned_profile"
    ):
        raise _customer_error("The owned review was not found.", "owned_review_not_found", 404)
    if review.response_status != "unanswered":
        raise _customer_error("This review already has a reply.", "review_already_answered")

    connection = _connection_for_campaign(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
    )
    if connection is None:
        raise _customer_error(
            "Connect this location to its Google business listing before posting replies.",
            "owned_profile_connection_required",
        )
    capability = _capability_for_connection(db, connection.id)
    if capability is None or capability.status not in ACTIVE_CAPABILITY_STATUSES:
        raise _customer_error(
            "Review posting is waiting for verified Google access.",
            "review_reply_capability_not_authorized",
        )
    review_resource = str(review.external_resource_name or "").strip().strip("/")
    prefix = _review_resource_prefix(connection)
    if not prefix or not review_resource.startswith(prefix):
        raise _customer_error(
            "This review no longer matches the connected business listing.",
            "review_connection_scope_mismatch",
        )

    now = _now()
    text_hash = _digest(approved_text)
    idempotency_key = f"review-reply:{_digest([organization_id, draft.id, text_hash])}"
    confirmation_record = {
        "version": CONFIRMATION_VERSION,
        "label": CONFIRMATION_LABEL,
        "confirmed": True,
        "confirmed_by_user_id": requested_by_user_id,
        "confirmed_at": now.isoformat(),
    }
    row = ReputationResponseExecution(
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
        business_location_id=review.business_location_id,
        review_id=review.id,
        draft_id=draft.id,
        connection_id=connection.id,
        capability_id=capability.id,
        idempotency_key=idempotency_key,
        status="queued",
        approved_text=approved_text,
        approved_text_hash=text_hash,
        policy_version=draft.policy_version,
        approval_snapshot={
            "draft_id": draft.id,
            "status": draft.status,
            "reviewed_by_user_id": draft.reviewed_by_user_id,
            "reviewed_at": draft.reviewed_at.isoformat() if draft.reviewed_at else None,
            "approved_text_hash": text_hash,
        },
        review_snapshot={
            "review_id": review.id,
            "external_review_id": review.external_review_id,
            "external_resource_name": review_resource,
            "response_status": review.response_status,
            "provider_updated_at": (
                review.provider_updated_at.isoformat() if review.provider_updated_at else None
            ),
        },
        capability_snapshot={
            "capability_id": capability.id,
            "status": capability.status,
            "provider_method": capability.provider_method,
            "authorized_at": capability.authorized_at.isoformat(),
        },
        confirmation_version=CONFIRMATION_VERSION,
        confirmation_hash=_digest(confirmation_record),
        provider_name=PROVIDER_NAME,
        provider_method=PROVIDER_METHOD,
        external_review_resource_name=review_resource,
        requested_by_user_id=requested_by_user_id,
        requested_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    job = job_service.create_job(
        db,
        tenant_id=tenant_id,
        job_type=JOB_TYPE,
        entity_type="reputation_response_execution",
        entity_id=row.id,
        idempotency_key=f"{JOB_TYPE}:{row.id}",
        payload={
            "tenant_id": tenant_id,
            "organization_id": organization_id,
            "campaign_id": campaign_id,
            "execution_id": row.id,
            "review_id": review.id,
        },
        available_at=now,
        max_retries=2,
    )
    row.platform_job_id = job.id
    emit_event(
        db,
        tenant_id=tenant_id,
        event_type="reputation.review_reply.publish_requested",
        payload={
            "organization_id": organization_id,
            "campaign_id": campaign_id,
            "business_location_id": review.business_location_id,
            "review_id": review.id,
            "draft_id": draft.id,
            "execution_id": row.id,
            "confirmation_version": CONFIRMATION_VERSION,
            "approved_text_hash": text_hash,
        },
    )
    db.commit()
    db.refresh(row)
    return row


def _block_execution(
    row: ReputationResponseExecution,
    capability: ReputationProviderCapability,
    *,
    reason_code: str,
    message: str,
    revoke_capability_access: bool = False,
) -> None:
    now = _now()
    row.status = "blocked"
    row.error_code = reason_code
    row.error_message = message[:2000]
    row.updated_at = now
    capability.last_failure_at = now
    capability.last_failure_code = reason_code
    capability.updated_at = now
    if revoke_capability_access:
        capability.status = "revoked"
        capability.revoked_at = now


def dispatch_execution(
    db: Session,
    *,
    execution_id: str,
    provider: GoogleBusinessProfileReviewsProvider | None = None,
) -> dict[str, Any]:
    row = db.get(ReputationResponseExecution, execution_id)
    if row is None:
        raise ValueError("Review reply execution was not found.")
    if row.status == "posted":
        return {"execution_id": row.id, "status": row.status, "idempotent_replay": True}
    if row.status in {"paused", "cancelled", "blocked"}:
        return {"execution_id": row.id, "status": row.status, "dispatched": False}

    capability = db.get(ReputationProviderCapability, row.capability_id)
    connection = db.get(DataConnection, row.connection_id)
    draft = db.get(ReputationResponseDraft, row.draft_id)
    review = db.get(ReputationReview, row.review_id)
    approval_snapshot = dict(row.approval_snapshot or {})
    if capability is None or capability.status not in ACTIVE_CAPABILITY_STATUSES:
        if capability is not None:
            _block_execution(
                row,
                capability,
                reason_code="review_reply_capability_not_authorized",
                message="Review posting access is not authorized.",
            )
        else:
            row.status = "blocked"
            row.error_code = "review_reply_capability_not_authorized"
            row.error_message = "Review posting access is not authorized."
            row.updated_at = _now()
        return {"execution_id": row.id, "status": "blocked", "dispatched": False}
    if (
        connection is None
        or connection.status == data_connections_service.CONNECTION_STATUS_DISCONNECTED
        or connection.tenant_id != row.tenant_id
    ):
        _block_execution(
            row,
            capability,
            reason_code="owned_profile_connection_required",
            message="The connected business listing is unavailable.",
        )
        return {"execution_id": row.id, "status": "blocked", "dispatched": False}
    if (
        draft is None
        or draft.status != "approved"
        or not draft.reviewed_by_user_id
        or draft.reviewed_at is None
        or not approval_snapshot.get("reviewed_at")
        or str(draft.reviewed_by_user_id)
        != str(approval_snapshot.get("reviewed_by_user_id") or "")
        or _digest(str(draft.approved_text or "").strip()) != row.approved_text_hash
    ):
        _block_execution(
            row,
            capability,
            reason_code="approved_reply_changed",
            message="The approved wording changed after publishing was confirmed.",
        )
        return {"execution_id": row.id, "status": "blocked", "dispatched": False}
    resource_prefix = _review_resource_prefix(connection)
    if (
        review is None
        or review.response_status != "unanswered"
        or str(review.external_resource_name or "").strip().strip("/")
        != row.external_review_resource_name
        or not resource_prefix
        or not row.external_review_resource_name.startswith(resource_prefix)
    ):
        _block_execution(
            row,
            capability,
            reason_code="review_changed_before_publish",
            message="The review changed after publishing was confirmed. Check it before replying.",
        )
        return {"execution_id": row.id, "status": "blocked", "dispatched": False}

    row.status = "posting"
    row.attempt_count = int(row.attempt_count or 0) + 1
    row.error_code = None
    row.error_message = None
    row.updated_at = _now()
    db.flush()
    try:
        resolved_provider = provider or GoogleBusinessProfileReviewsProvider(
            access_token=reputation_inventory_service.google_access_token(
                db, row.organization_id
            ),
            timeout_seconds=float(get_settings().google_oauth_http_timeout_seconds),
        )
        receipt = resolved_provider.update_reply(
            review_name=row.external_review_resource_name,
            comment=row.approved_text,
        )
    except GoogleReviewsProviderError as exc:
        if exc.retryable:
            raise
        _block_execution(
            row,
            capability,
            reason_code=exc.reason_code,
            message=str(exc),
            revoke_capability_access=exc.reason_code == "review_reply_access_denied",
        )
        emit_event(
            db,
            tenant_id=row.tenant_id,
            event_type="reputation.review_reply.publish_blocked",
            payload={"execution_id": row.id, "reason_code": exc.reason_code},
        )
        return {"execution_id": row.id, "status": "blocked", "dispatched": True}
    except ValueError as exc:
        _block_execution(
            row,
            capability,
            reason_code="google_credentials_unavailable",
            message=str(exc),
        )
        return {"execution_id": row.id, "status": "blocked", "dispatched": False}

    reply_state = str(receipt.get("reply_state") or "").upper() or None
    policy_violation = str(receipt.get("policy_violation") or "").upper() or None
    row.provider_reply_state = reply_state
    row.provider_policy_violation = policy_violation
    row.provider_receipt = {
        "comment_hash": _digest(str(receipt.get("comment") or row.approved_text).strip()),
        "update_time": (
            receipt.get("update_time").isoformat()
            if isinstance(receipt.get("update_time"), datetime)
            else None
        ),
        "reply_state": reply_state,
        "policy_violation": policy_violation,
        "provider_method": PROVIDER_METHOD,
    }
    if reply_state == "REJECTED" or policy_violation:
        _block_execution(
            row,
            capability,
            reason_code="review_reply_policy_rejected",
            message="Google did not accept this reply. Review the wording before trying again.",
        )
        return {"execution_id": row.id, "status": "blocked", "dispatched": True}

    posted_at = _now()
    provider_time = receipt.get("update_time")
    reputation_inventory_service.record_owned_reply(
        db,
        review=review,
        response_text=row.approved_text,
        response_updated_at=provider_time if isinstance(provider_time, datetime) else posted_at,
        captured_at=posted_at,
    )
    row.status = "posted"
    row.posted_at = posted_at
    row.updated_at = posted_at
    capability.status = "verified"
    capability.verified_at = capability.verified_at or posted_at
    capability.last_success_at = posted_at
    capability.last_failure_at = None
    capability.last_failure_code = None
    capability.updated_at = posted_at
    emit_event(
        db,
        tenant_id=row.tenant_id,
        event_type="reputation.review_reply.publish_confirmed",
        payload={
            "organization_id": row.organization_id,
            "campaign_id": row.campaign_id,
            "business_location_id": row.business_location_id,
            "review_id": row.review_id,
            "draft_id": row.draft_id,
            "execution_id": row.id,
            "provider_method": row.provider_method,
            "approved_text_hash": row.approved_text_hash,
        },
    )
    db.flush()
    return {"execution_id": row.id, "status": "posted", "dispatched": True}


def record_dispatch_failure(
    db: Session,
    *,
    execution_id: str,
    error: Exception,
) -> None:
    row = db.get(ReputationResponseExecution, execution_id)
    if row is None or row.status in {"posted", "paused", "cancelled", "blocked"}:
        return
    now = _now()
    row.attempt_count = int(row.attempt_count or 0) + 1
    row.status = "retrying" if bool(getattr(error, "retryable", True)) else "failed"
    row.error_code = str(getattr(error, "reason_code", "review_reply_publish_failed"))[:120]
    row.error_message = str(error)[:2000]
    row.updated_at = now
    capability = db.get(ReputationProviderCapability, row.capability_id)
    if capability is not None:
        capability.last_failure_at = now
        capability.last_failure_code = row.error_code
        capability.updated_at = now
    emit_event(
        db,
        tenant_id=row.tenant_id,
        event_type="reputation.review_reply.publish_retry_scheduled",
        payload={"execution_id": row.id, "reason_code": row.error_code},
    )
    db.flush()


def list_executions(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
) -> list[dict[str, Any]]:
    rows = (
        db.query(ReputationResponseExecution)
        .filter(
            ReputationResponseExecution.tenant_id == tenant_id,
            ReputationResponseExecution.organization_id == organization_id,
            ReputationResponseExecution.campaign_id == campaign_id,
        )
        .order_by(ReputationResponseExecution.created_at.desc())
        .limit(250)
        .all()
    )
    return [serialize_execution(row) for row in rows]


def serialize_execution(row: ReputationResponseExecution) -> dict[str, Any]:
    return {
        "id": row.id,
        "campaign_id": row.campaign_id,
        "business_location_id": row.business_location_id,
        "review_id": row.review_id,
        "draft_id": row.draft_id,
        "status": row.status,
        "provider_name": row.provider_name,
        "provider_method": row.provider_method,
        "provider_reply_state": row.provider_reply_state,
        "provider_policy_violation": row.provider_policy_violation,
        "provider_receipt": dict(row.provider_receipt or {}),
        "attempt_count": row.attempt_count,
        "error_code": row.error_code,
        "error_message": row.error_message,
        "confirmation_version": row.confirmation_version,
        "requested_at": row.requested_at.isoformat(),
        "posted_at": row.posted_at.isoformat() if row.posted_at else None,
        "paused_at": row.paused_at.isoformat() if row.paused_at else None,
        "cancelled_at": row.cancelled_at.isoformat() if row.cancelled_at else None,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def control_execution(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    execution_id: str,
    action: str,
) -> ReputationResponseExecution:
    row = (
        db.query(ReputationResponseExecution)
        .filter(
            ReputationResponseExecution.id == execution_id,
            ReputationResponseExecution.tenant_id == tenant_id,
            ReputationResponseExecution.organization_id == organization_id,
        )
        .first()
    )
    if row is None:
        raise _customer_error("Review reply work was not found.", "review_reply_execution_not_found", 404)
    job = db.get(PlatformJob, row.platform_job_id) if row.platform_job_id else None
    now = _now()
    if action == "pause":
        if row.status not in {"queued", "retrying"} or (job and job.status == "running"):
            raise _customer_error("This reply cannot be paused right now.", "review_reply_pause_unavailable")
        row.status = "paused"
        row.paused_at = now
        if job:
            job.status = job_service.JOB_STATUS_QUEUED
            job.available_at = now + PAUSE_UNTIL
    elif action == "resume":
        if row.status != "paused":
            raise _customer_error("This reply is not paused.", "review_reply_not_paused")
        row.status = "queued"
        row.paused_at = None
        if job:
            job.status = job_service.JOB_STATUS_QUEUED
            job.available_at = now
            job.error = None
    elif action == "cancel":
        if row.status not in {"queued", "retrying", "paused"}:
            raise _customer_error("This reply can no longer be cancelled.", "review_reply_cancel_unavailable")
        row.status = "cancelled"
        row.cancelled_at = now
        if job:
            job.status = job_service.JOB_STATUS_FAILED
            job.finished_at = now
            job.error = "Cancelled by the customer before posting."
    elif action == "retry":
        if row.status != "failed":
            raise _customer_error("This reply is not ready to retry.", "review_reply_retry_unavailable")
        capability = db.get(ReputationProviderCapability, row.capability_id)
        if capability is None or capability.status not in ACTIVE_CAPABILITY_STATUSES:
            raise _customer_error(
                "Google review posting access needs attention before retrying.",
                "review_reply_capability_not_authorized",
            )
        row.status = "queued"
        row.error_code = None
        row.error_message = None
        if job:
            job.status = job_service.JOB_STATUS_QUEUED
            job.available_at = now
            job.retry_count = 0
            job.finished_at = None
            job.error = None
            job.result = None
            job.locked_at = None
            job.lease_expires_at = None
            job.locked_by = None
    else:
        raise _customer_error("Review reply action is invalid.", "review_reply_action_invalid", 400)
    row.updated_at = now
    emit_event(
        db,
        tenant_id=row.tenant_id,
        event_type=f"reputation.review_reply.{action}",
        payload={"execution_id": row.id, "review_id": row.review_id},
    )
    db.commit()
    db.refresh(row)
    return row
