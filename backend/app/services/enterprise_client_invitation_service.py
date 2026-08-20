from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.crypto import CredentialCryptoError, decrypt_payload, encrypt_payload
from app.core.passwords import hash_password, verify_password
from app.models.enterprise_client_invitation import EnterpriseClientInvitation
from app.models.organization_membership import OrganizationMembership
from app.models.portfolio_targeting import (
    PortfolioLocationAccessGrant,
    PortfolioLocationGroup,
    PortfolioLocationGroupMember,
)
from app.models.user import User
from app.services.audit_service import write_audit_log
from app.services.commercial_plan_service import (
    FEATURE_AUTHENTICATED_CLIENT_REPORTS,
    require_commercial_feature,
)


class EnterpriseClientInvitationError(RuntimeError):
    def __init__(self, message: str, *, reason_code: str, status_code: int = 400) -> None:
        self.reason_code = reason_code
        self.status_code = status_code
        super().__init__(message)


def create_client_invitation(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    actor_user_id: str,
    email: str,
    location_group_id: str,
    expires_in_days: int,
) -> tuple[dict[str, Any], str, bool]:
    _assert_scope(tenant_id=tenant_id, organization_id=organization_id)
    require_commercial_feature(
        db,
        organization_id=organization_id,
        feature_code=FEATURE_AUTHENTICATED_CLIENT_REPORTS,
    )
    normalized_email = _normalized_email(email)
    group = _active_group(
        db,
        organization_id=organization_id,
        location_group_id=location_group_id,
    )
    _reject_existing_workspace_member(
        db,
        organization_id=organization_id,
        normalized_email=normalized_email,
    )

    email_hash = _hash(normalized_email)
    existing = (
        db.query(EnterpriseClientInvitation)
        .filter(
            EnterpriseClientInvitation.organization_id == organization_id,
            EnterpriseClientInvitation.email_hash == email_hash,
            EnterpriseClientInvitation.location_group_id == group.id,
        )
        .with_for_update()
        .first()
    )
    now = datetime.now(UTC)
    raw_token = secrets.token_urlsafe(32)
    encrypted_email, key_reference, key_version = encrypt_payload(
        {"email": normalized_email, "organization_id": organization_id}
    )
    created = existing is None
    if existing is None:
        row = EnterpriseClientInvitation(
            id=str(uuid.uuid4()),
            tenant_id=organization_id,
            organization_id=organization_id,
            location_group_id=group.id,
            email_hash=email_hash,
            encrypted_email=encrypted_email,
            encryption_key_reference=key_reference,
            encryption_key_version=key_version,
            token_hash=_hash(raw_token),
            status="active",
            version=1,
            created_by_user_id=actor_user_id,
            expires_at=now + timedelta(days=expires_in_days),
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    else:
        row = existing
        row.encrypted_email = encrypted_email
        row.encryption_key_reference = key_reference
        row.encryption_key_version = key_version
        row.token_hash = _hash(raw_token)
        row.status = "active"
        row.expires_at = now + timedelta(days=expires_in_days)
        row.accepted_user_id = None
        row.accepted_at = None
        row.revoked_at = None
        row.updated_at = now
        row.version += 1
    write_audit_log(
        db,
        tenant_id=organization_id,
        actor_user_id=actor_user_id,
        event_type=(
            "enterprise.client_invitation.created"
            if created
            else "enterprise.client_invitation.replaced"
        ),
        payload={
            "client_invitation_id": row.id,
            "email_hash": email_hash,
            "location_group_id": group.id,
        },
    )
    db.flush()
    return _serialize_invitation(db, row, include_email=True), raw_token, created


def list_client_invitations(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
) -> dict[str, Any]:
    _assert_scope(tenant_id=tenant_id, organization_id=organization_id)
    require_commercial_feature(
        db,
        organization_id=organization_id,
        feature_code=FEATURE_AUTHENTICATED_CLIENT_REPORTS,
    )
    rows = (
        db.query(EnterpriseClientInvitation)
        .filter(EnterpriseClientInvitation.organization_id == organization_id)
        .order_by(
            EnterpriseClientInvitation.created_at.desc(),
            EnterpriseClientInvitation.id.desc(),
        )
        .limit(200)
        .all()
    )
    items = [_serialize_invitation(db, row, include_email=True) for row in rows]
    return {
        "items": items,
        "count": len(items),
        "truth": {
            "summary": "Client invitations grant read-only reports for one saved location group.",
            "passwords_visible_to_owner": False,
            "invitation_links_returned_once": True,
        },
    }


def revoke_client_invitation(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    actor_user_id: str,
    invitation_id: str,
    expected_version: int,
) -> dict[str, Any]:
    _assert_scope(tenant_id=tenant_id, organization_id=organization_id)
    require_commercial_feature(
        db,
        organization_id=organization_id,
        feature_code=FEATURE_AUTHENTICATED_CLIENT_REPORTS,
    )
    row = (
        db.query(EnterpriseClientInvitation)
        .filter(
            EnterpriseClientInvitation.id == invitation_id,
            EnterpriseClientInvitation.organization_id == organization_id,
        )
        .with_for_update()
        .first()
    )
    if row is None:
        raise EnterpriseClientInvitationError(
            "Client invitation not found.",
            reason_code="client_invitation_not_found",
            status_code=404,
        )
    if row.version != expected_version:
        raise EnterpriseClientInvitationError(
            "This invitation changed. Refresh the page before trying again.",
            reason_code="client_invitation_version_conflict",
            status_code=409,
        )
    current_status = invitation_status(row)
    if current_status != "revoked":
        now = datetime.now(UTC)
        if current_status == "accepted" and row.accepted_user_id:
            grant = (
                db.query(PortfolioLocationAccessGrant)
                .filter(
                    PortfolioLocationAccessGrant.organization_id == organization_id,
                    PortfolioLocationAccessGrant.user_id == row.accepted_user_id,
                    PortfolioLocationAccessGrant.location_group_id == row.location_group_id,
                )
                .with_for_update()
                .first()
            )
            if grant is not None and grant.status == "active":
                grant.status = "revoked"
                grant.revoked_by_user_id = actor_user_id
                grant.revoked_at = now
                grant.updated_at = now
                grant.version += 1
        row.status = "revoked"
        row.revoked_at = now
        row.updated_at = now
        row.version += 1
        write_audit_log(
            db,
            tenant_id=organization_id,
            actor_user_id=actor_user_id,
            event_type="enterprise.client_invitation.revoked",
            payload={
                "client_invitation_id": row.id,
                "location_group_id": row.location_group_id,
                "access_removed": current_status == "accepted",
            },
        )
        db.flush()
    return _serialize_invitation(db, row, include_email=True)


def preview_client_invitation(db: Session, *, token: str) -> dict[str, Any]:
    row = _invitation_by_token(db, token=token, lock=False)
    status = invitation_status(row)
    if status != "active":
        raise EnterpriseClientInvitationError(
            "This client invitation is no longer active.",
            reason_code=f"client_invitation_{status}",
            status_code=410,
        )
    email = _invitation_email(row)
    group = _active_group(
        db,
        organization_id=row.organization_id,
        location_group_id=row.location_group_id,
    )
    return {
        "status": "active",
        "email_hint": _masked_email(email),
        "location_group_name": group.name,
        "expires_at": _as_utc(row.expires_at).isoformat(),
        "truth": {
            "summary": "This invitation creates read-only access to assigned saved reports.",
            "can_change_workspace": False,
        },
    }


def accept_client_invitation(
    db: Session,
    *,
    token: str,
    password: str,
) -> dict[str, str]:
    row = _invitation_by_token(db, token=token, lock=True)
    status = invitation_status(row)
    if status != "active":
        raise EnterpriseClientInvitationError(
            "This client invitation is no longer active.",
            reason_code=f"client_invitation_{status}",
            status_code=410,
        )
    _active_group(
        db,
        organization_id=row.organization_id,
        location_group_id=row.location_group_id,
    )
    require_commercial_feature(
        db,
        organization_id=row.organization_id,
        feature_code=FEATURE_AUTHENTICATED_CLIENT_REPORTS,
    )
    email = _invitation_email(row)
    user = db.query(User).filter(func.lower(User.email) == email).with_for_update().first()
    now = datetime.now(UTC)
    if user is None:
        _validate_new_password(password)
        user = User(
            id=str(uuid.uuid4()),
            tenant_id=row.organization_id,
            email=email,
            hashed_password=hash_password(password),
            is_active=True,
            is_platform_user=False,
            platform_role=None,
            created_at=now,
        )
        db.add(user)
        db.flush()
    elif not user.is_active or not verify_password(password, user.hashed_password):
        raise EnterpriseClientInvitationError(
            "This email already has an InsightOS sign-in. Enter its current password to continue.",
            reason_code="client_invitation_existing_sign_in_required",
            status_code=409,
        )

    membership = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.organization_id == row.organization_id,
            OrganizationMembership.user_id == user.id,
        )
        .with_for_update()
        .first()
    )
    if membership is None:
        membership = OrganizationMembership(
            id=str(uuid.uuid4()),
            user_id=user.id,
            organization_id=row.organization_id,
            role="org_client",
            status="active",
            created_at=now,
        )
        db.add(membership)
    elif membership.role != "org_client":
        raise EnterpriseClientInvitationError(
            "This email already belongs to a workspace team member. Ask the owner to manage that access directly.",
            reason_code="client_invitation_existing_member",
            status_code=409,
        )
    else:
        membership.status = "active"

    grant = (
        db.query(PortfolioLocationAccessGrant)
        .filter(
            PortfolioLocationAccessGrant.organization_id == row.organization_id,
            PortfolioLocationAccessGrant.user_id == user.id,
            PortfolioLocationAccessGrant.location_group_id == row.location_group_id,
        )
        .with_for_update()
        .first()
    )
    if grant is None:
        grant = PortfolioLocationAccessGrant(
            id=str(uuid.uuid4()),
            tenant_id=row.organization_id,
            organization_id=row.organization_id,
            user_id=user.id,
            location_group_id=row.location_group_id,
            access_role="viewer",
            status="active",
            version=1,
            created_by_user_id=row.created_by_user_id,
            created_at=now,
            updated_at=now,
        )
        db.add(grant)
    else:
        grant.access_role = "viewer"
        grant.status = "active"
        grant.revoked_by_user_id = None
        grant.revoked_at = None
        grant.updated_at = now
        grant.version += 1

    row.status = "accepted"
    row.accepted_user_id = user.id
    row.accepted_at = now
    row.updated_at = now
    row.version += 1
    write_audit_log(
        db,
        tenant_id=row.organization_id,
        actor_user_id=user.id,
        event_type="enterprise.client_invitation.accepted",
        payload={
            "client_invitation_id": row.id,
            "location_group_id": row.location_group_id,
        },
    )
    db.flush()
    return {
        "email": email,
        "organization_id": row.organization_id,
        "user_id": user.id,
    }


def invitation_status(row: EnterpriseClientInvitation) -> str:
    if row.status == "active" and _as_utc(row.expires_at) <= datetime.now(UTC):
        return "expired"
    return row.status


def _invitation_by_token(
    db: Session,
    *,
    token: str,
    lock: bool,
) -> EnterpriseClientInvitation:
    if len(token) < 24 or len(token) > 160 or any(
        character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
        for character in token
    ):
        raise EnterpriseClientInvitationError(
            "Client invitation not found.",
            reason_code="client_invitation_not_found",
            status_code=404,
        )
    query = (
        db.query(EnterpriseClientInvitation)
        .execution_options(populate_existing=True)
        .filter(EnterpriseClientInvitation.token_hash == _hash(token))
    )
    if lock:
        query = query.with_for_update()
    row = query.first()
    if row is None:
        raise EnterpriseClientInvitationError(
            "Client invitation not found.",
            reason_code="client_invitation_not_found",
            status_code=404,
        )
    return row


def _active_group(
    db: Session,
    *,
    organization_id: str,
    location_group_id: str,
) -> PortfolioLocationGroup:
    group = (
        db.query(PortfolioLocationGroup)
        .filter(
            PortfolioLocationGroup.id == location_group_id,
            PortfolioLocationGroup.organization_id == organization_id,
            PortfolioLocationGroup.status == "active",
        )
        .first()
    )
    if group is None:
        raise EnterpriseClientInvitationError(
            "Choose an active saved location group.",
            reason_code="client_invitation_location_group_unavailable",
            status_code=409,
        )
    member_count = (
        db.query(PortfolioLocationGroupMember)
        .filter(
            PortfolioLocationGroupMember.organization_id == organization_id,
            PortfolioLocationGroupMember.location_group_id == location_group_id,
        )
        .count()
    )
    if member_count == 0:
        raise EnterpriseClientInvitationError(
            "Add at least one location to this saved group before inviting a client.",
            reason_code="client_invitation_location_group_empty",
            status_code=409,
        )
    return group


def _reject_existing_workspace_member(
    db: Session,
    *,
    organization_id: str,
    normalized_email: str,
) -> None:
    membership = (
        db.query(OrganizationMembership)
        .join(User, User.id == OrganizationMembership.user_id)
        .filter(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.status == "active",
            func.lower(User.email) == normalized_email,
        )
        .first()
    )
    if membership is not None and membership.role != "org_client":
        raise EnterpriseClientInvitationError(
            "That email already belongs to a workspace team member. Manage their team access instead.",
            reason_code="client_invitation_existing_member",
            status_code=409,
        )


def _serialize_invitation(
    db: Session,
    row: EnterpriseClientInvitation,
    *,
    include_email: bool,
) -> dict[str, Any]:
    group = db.get(PortfolioLocationGroup, row.location_group_id)
    location_count = (
        db.query(PortfolioLocationGroupMember)
        .filter(
            PortfolioLocationGroupMember.organization_id == row.organization_id,
            PortfolioLocationGroupMember.location_group_id == row.location_group_id,
        )
        .count()
    )
    payload: dict[str, Any] = {
        "id": row.id,
        "location_group_id": row.location_group_id,
        "location_group_name": group.name if group is not None else "Saved location group",
        "location_count": location_count,
        "status": invitation_status(row),
        "version": row.version,
        "expires_at": _as_utc(row.expires_at).isoformat(),
        "accepted_at": _as_utc(row.accepted_at).isoformat() if row.accepted_at else None,
        "created_at": _as_utc(row.created_at).isoformat(),
    }
    if include_email:
        payload["email"] = _invitation_email(row)
    return payload


def _invitation_email(row: EnterpriseClientInvitation) -> str:
    try:
        payload = decrypt_payload(row.encrypted_email)
    except CredentialCryptoError as exc:
        raise EnterpriseClientInvitationError(
            "This invitation cannot be read safely. Ask support for help.",
            reason_code="client_invitation_email_unavailable",
            status_code=409,
        ) from exc
    email = _normalized_email(str(payload.get("email") or ""))
    if (
        _hash(email) != row.email_hash
        or str(payload.get("organization_id") or "") != row.organization_id
    ):
        raise EnterpriseClientInvitationError(
            "This invitation failed its safety check. Ask support for help.",
            reason_code="client_invitation_scope_invalid",
            status_code=409,
        )
    return email


def _normalized_email(value: str) -> str:
    normalized = value.strip().lower()
    if not normalized or "@" not in normalized:
        raise EnterpriseClientInvitationError(
            "Enter a valid client email.",
            reason_code="client_invitation_email_invalid",
            status_code=422,
        )
    return normalized


def _validate_new_password(value: str) -> None:
    if (
        len(value) < 12
        or not any(character.isalpha() for character in value)
        or not any(character.isdigit() for character in value)
    ):
        raise EnterpriseClientInvitationError(
            "Use at least 12 characters with a letter and a number.",
            reason_code="client_invitation_password_too_weak",
            status_code=422,
        )


def _masked_email(email: str) -> str:
    local, domain = email.split("@", 1)
    return f"{local[:1]}{'*' * min(max(len(local) - 1, 1), 6)}@{domain}"


def _hash(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _assert_scope(*, tenant_id: str, organization_id: str) -> None:
    if tenant_id != organization_id:
        raise EnterpriseClientInvitationError(
            "Organization context does not match this request.",
            reason_code="organization_scope_mismatch",
            status_code=404,
        )
