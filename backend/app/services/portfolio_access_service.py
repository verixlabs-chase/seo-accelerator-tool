from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.organization import Organization
from app.models.organization_membership import OrganizationMembership
from app.models.portfolio_targeting import (
    PortfolioLocationAccessGrant,
    PortfolioLocationGroup,
    PortfolioLocationGroupMember,
)
from app.models.user import User
from app.services.audit_service import write_audit_log
from app.services.cost_economics_service import CostEconomicsError, resolve_plan_economics


ACCESS_ROLE_LEVEL = {"viewer": 1, "operator": 2, "approver": 3}
ADMIN_ROLES = {"org_owner", "org_admin"}


class PortfolioAccessError(RuntimeError):
    def __init__(self, reason_code: str, *, status_code: int = 400) -> None:
        self.reason_code = reason_code
        self.status_code = status_code
        super().__init__(reason_code)


def list_portfolio_access_grants(
    db: Session,
    *,
    organization_id: str,
    include_revoked: bool = False,
) -> list[dict[str, Any]]:
    query = db.query(PortfolioLocationAccessGrant).filter(
        PortfolioLocationAccessGrant.organization_id == organization_id
    )
    if not include_revoked:
        query = query.filter(PortfolioLocationAccessGrant.status == "active")
    rows = query.order_by(
        PortfolioLocationAccessGrant.status.asc(),
        PortfolioLocationAccessGrant.created_at.asc(),
        PortfolioLocationAccessGrant.id.asc(),
    ).all()
    return [serialize_portfolio_access_grant(db, row) for row in rows]


def save_portfolio_access_grant(
    db: Session,
    *,
    organization_id: str,
    actor_user_id: str,
    grantee_email: str,
    location_group_id: str,
    access_role: str,
    expected_version: int | None = None,
) -> tuple[PortfolioLocationAccessGrant, bool]:
    _assert_growth_plan(db, organization_id=organization_id)
    normalized_role = access_role.strip().lower()
    if normalized_role not in ACCESS_ROLE_LEVEL:
        raise PortfolioAccessError("portfolio_access_role_invalid", status_code=422)
    normalized_email = grantee_email.strip().lower()
    if not normalized_email:
        raise PortfolioAccessError("portfolio_access_grantee_required", status_code=422)

    group = _group_or_error(
        db,
        organization_id=organization_id,
        location_group_id=location_group_id,
    )
    if group.status != "active":
        raise PortfolioAccessError("portfolio_access_group_inactive", status_code=409)

    grantee = (
        db.query(User)
        .join(OrganizationMembership, OrganizationMembership.user_id == User.id)
        .filter(
            func.lower(User.email) == normalized_email,
            User.is_active.is_(True),
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.status == "active",
        )
        .first()
    )
    if grantee is None:
        raise PortfolioAccessError("portfolio_access_grantee_not_found", status_code=404)
    membership = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == grantee.id,
            OrganizationMembership.status == "active",
        )
        .one()
    )
    if membership.role in ADMIN_ROLES:
        raise PortfolioAccessError("portfolio_access_admin_grant_not_needed", status_code=409)

    existing = (
        db.query(PortfolioLocationAccessGrant)
        .filter(
            PortfolioLocationAccessGrant.organization_id == organization_id,
            PortfolioLocationAccessGrant.user_id == grantee.id,
            PortfolioLocationAccessGrant.location_group_id == group.id,
        )
        .with_for_update()
        .first()
    )
    now = datetime.now(UTC)
    created = existing is None
    if existing is None:
        row = PortfolioLocationAccessGrant(
            id=str(uuid.uuid4()),
            tenant_id=organization_id,
            organization_id=organization_id,
            user_id=grantee.id,
            location_group_id=group.id,
            access_role=normalized_role,
            status="active",
            version=1,
            created_by_user_id=actor_user_id,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    else:
        row = existing
        if row.status == "active" and row.access_role == normalized_role:
            return row, False
        if expected_version is None or row.version != expected_version:
            raise PortfolioAccessError("portfolio_access_version_conflict", status_code=409)
        row.access_role = normalized_role
        row.status = "active"
        row.revoked_by_user_id = None
        row.revoked_at = None
        row.updated_at = now
        row.version += 1

    write_audit_log(
        db,
        tenant_id=organization_id,
        actor_user_id=actor_user_id,
        event_type=(
            "portfolio.access_grant.created"
            if created
            else "portfolio.access_grant.updated"
        ),
        payload={
            "organization_id": organization_id,
            "portfolio_access_grant_id": row.id,
            "grantee_user_id": grantee.id,
            "location_group_id": group.id,
            "access_role": normalized_role,
        },
    )
    db.flush()
    return row, created


def revoke_portfolio_access_grant(
    db: Session,
    *,
    organization_id: str,
    grant_id: str,
    actor_user_id: str,
    expected_version: int,
) -> PortfolioLocationAccessGrant:
    row = (
        db.query(PortfolioLocationAccessGrant)
        .filter(
            PortfolioLocationAccessGrant.organization_id == organization_id,
            PortfolioLocationAccessGrant.id == grant_id,
        )
        .with_for_update()
        .first()
    )
    if row is None:
        raise PortfolioAccessError("portfolio_access_grant_not_found", status_code=404)
    if row.version != expected_version:
        raise PortfolioAccessError("portfolio_access_version_conflict", status_code=409)
    if row.status == "revoked":
        return row
    now = datetime.now(UTC)
    row.status = "revoked"
    row.revoked_by_user_id = actor_user_id
    row.revoked_at = now
    row.updated_at = now
    row.version += 1
    write_audit_log(
        db,
        tenant_id=organization_id,
        actor_user_id=actor_user_id,
        event_type="portfolio.access_grant.revoked",
        payload={
            "organization_id": organization_id,
            "portfolio_access_grant_id": row.id,
            "grantee_user_id": row.user_id,
            "location_group_id": row.location_group_id,
            "access_role": row.access_role,
        },
    )
    db.flush()
    return row


def accessible_location_group_ids(
    db: Session,
    *,
    organization_id: str,
    user_id: str,
    org_role: str,
    required_access_role: str = "viewer",
) -> set[str] | None:
    if org_role in ADMIN_ROLES:
        return None
    required_level = ACCESS_ROLE_LEVEL[required_access_role]
    rows = (
        db.query(PortfolioLocationAccessGrant)
        .filter(
            PortfolioLocationAccessGrant.organization_id == organization_id,
            PortfolioLocationAccessGrant.user_id == user_id,
            PortfolioLocationAccessGrant.status == "active",
        )
        .all()
    )
    return {
        row.location_group_id
        for row in rows
        if ACCESS_ROLE_LEVEL.get(row.access_role, 0) >= required_level
    }


def require_location_group_access(
    db: Session,
    *,
    organization_id: str,
    user_id: str,
    org_role: str,
    location_group_id: str | None,
    required_access_role: str,
) -> None:
    if org_role in ADMIN_ROLES:
        return
    if not location_group_id:
        raise PortfolioAccessError("portfolio_access_group_required", status_code=403)
    allowed_group_ids = accessible_location_group_ids(
        db,
        organization_id=organization_id,
        user_id=user_id,
        org_role=org_role,
        required_access_role=required_access_role,
    )
    if allowed_group_ids is not None and location_group_id not in allowed_group_ids:
        reason = (
            "portfolio_access_approval_required"
            if required_access_role == "approver"
            else "portfolio_access_operator_required"
            if required_access_role == "operator"
            else "portfolio_access_denied"
        )
        raise PortfolioAccessError(reason, status_code=403)


def require_target_overrides_within_group(
    db: Session,
    *,
    organization_id: str,
    org_role: str,
    location_group_id: str | None,
    included_location_ids: list[str],
    excluded_location_ids: list[str],
) -> None:
    if org_role in ADMIN_ROLES:
        return
    if not location_group_id:
        raise PortfolioAccessError("portfolio_access_group_required", status_code=403)
    member_ids = {
        row.business_location_id
        for row in db.query(PortfolioLocationGroupMember)
        .filter(
            PortfolioLocationGroupMember.organization_id == organization_id,
            PortfolioLocationGroupMember.location_group_id == location_group_id,
        )
        .all()
    }
    requested_ids = set(included_location_ids) | set(excluded_location_ids)
    if not requested_ids.issubset(member_ids):
        raise PortfolioAccessError("portfolio_access_target_outside_group", status_code=403)


def serialize_portfolio_access_grant(
    db: Session,
    row: PortfolioLocationAccessGrant,
) -> dict[str, Any]:
    user = db.get(User, row.user_id)
    group = db.get(PortfolioLocationGroup, row.location_group_id)
    return {
        "id": row.id,
        "organization_id": row.organization_id,
        "user_id": row.user_id,
        "grantee_email": user.email if user else None,
        "location_group_id": row.location_group_id,
        "location_group_name": group.name if group else None,
        "access_role": row.access_role,
        "status": row.status,
        "version": row.version,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
        "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
    }


def _group_or_error(
    db: Session,
    *,
    organization_id: str,
    location_group_id: str,
) -> PortfolioLocationGroup:
    row = (
        db.query(PortfolioLocationGroup)
        .filter(
            PortfolioLocationGroup.organization_id == organization_id,
            PortfolioLocationGroup.id == location_group_id,
        )
        .first()
    )
    if row is None:
        raise PortfolioAccessError("portfolio_access_group_not_found", status_code=404)
    return row


def _assert_growth_plan(db: Session, *, organization_id: str) -> None:
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise PortfolioAccessError("organization_not_found", status_code=404)
    try:
        plan = resolve_plan_economics(organization.plan_type)
    except CostEconomicsError as exc:
        raise PortfolioAccessError("portfolio_access_upgrade_required", status_code=403) from exc
    if plan.code not in {"multi_location", "enterprise"}:
        raise PortfolioAccessError("portfolio_access_upgrade_required", status_code=403)
