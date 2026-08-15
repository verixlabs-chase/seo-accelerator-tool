import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.passwords import hash_password, verify_password
from app.core.security import create_token, decode_token
from app.models.auth_session import AuthSession
from app.models.organization import Organization
from app.models.organization_membership import OrganizationMembership
from app.models.role import Role, UserRole
from app.models.tenant import Tenant
from app.models.user import User
from app.services import commercial_plan_service, provisioning_service


VALID_PLATFORM_ROLES = {"platform_owner", "platform_admin"}
VALID_ORG_ROLES = {"org_owner", "org_admin", "org_user"}
AUTH_SESSION_ACTIVE = "active"
AUTH_SESSION_REVOKED = "revoked"


def seed_local_admin(db: Session) -> None:
    settings = get_settings()
    if settings.app_env.lower() != "local" or not settings.local_admin_bootstrap_enabled:
        return

    tenant = db.query(Tenant).filter(Tenant.name == "Default Tenant").first()
    if tenant is None:
        tenant = Tenant(name="Default Tenant")
        db.add(tenant)
        db.flush()

    organization = db.query(Organization).filter(Organization.id == tenant.id).first()
    if organization is None:
        tier_profile = provisioning_service.ensure_default_tier_profile(db)
        organization = Organization(
            id=tenant.id,
            name=f"default-org-{tenant.id[:8]}",
            plan_type="solo",
            billing_mode="subscription",
            status="active",
            tier_profile_id=tier_profile.id,
            tier_version=tier_profile.version,
        )
        db.add(organization)
        db.flush()
        commercial_plan_service.apply_commercial_plan(
            db,
            organization_id=organization.id,
            plan_code="solo",
        )

    role = db.query(Role).filter(Role.id == "tenant_admin").first()
    if role is None:
        role = Role(id="tenant_admin", name="tenant_admin")
        db.add(role)
        db.flush()
    platform_role = db.query(Role).filter(Role.id == "platform_admin").first()
    if platform_role is None:
        platform_role = Role(id="platform_admin", name="platform_admin")
        db.add(platform_role)
        db.flush()

    user = db.query(User).filter(User.email == "admin@local.dev").first()
    if user is None:
        user = User(
            tenant_id=tenant.id,
            email="admin@local.dev",
            hashed_password=hash_password("admin123!"),
            is_platform_user=True,
            platform_role="platform_admin",
        )
        db.add(user)
        db.flush()
        db.add(UserRole(id=str(uuid.uuid4()), user_id=user.id, role_id=role.id))
        db.add(UserRole(id=str(uuid.uuid4()), user_id=user.id, role_id=platform_role.id))
    membership = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.organization_id == organization.id,
        )
        .first()
    )
    if membership is None:
        db.add(
            OrganizationMembership(
                user_id=user.id,
                organization_id=organization.id,
                role="org_owner",
                status="active",
            )
        )
    db.commit()
    provisioning_service.ensure_organization_provisioned(db, organization_id=organization.id)


def _list_memberships(db: Session, user_id: str) -> list[OrganizationMembership]:
    return (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.status == "active",
        )
        .all()
    )


def _organization_items(
    db: Session,
    memberships: list[OrganizationMembership],
) -> list[dict[str, str]]:
    organization_ids = [row.organization_id for row in memberships]
    if not organization_ids:
        return []

    names = {
        organization_id: name
        for organization_id, name in (
            db.query(Organization.id, Organization.name)
            .filter(Organization.id.in_(organization_ids))
            .all()
        )
    }
    return [
        {
            "organization_id": row.organization_id,
            "role": row.role,
            "name": str(names.get(row.organization_id) or "Workspace"),
        }
        for row in memberships
    ]


def _resolve_org_context(
    memberships: list[OrganizationMembership],
    organization_id: str | None,
) -> tuple[str | None, str | None, bool, list[dict[str, str]]]:
    org_items = [{"organization_id": row.organization_id, "role": row.role} for row in memberships]
    by_org = {row.organization_id: row for row in memberships}

    if organization_id is not None:
        selected = by_org.get(organization_id)
        if selected is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organization access denied")
        return selected.organization_id, selected.role, False, org_items

    if len(memberships) == 1:
        selected = memberships[0]
        return selected.organization_id, selected.role, False, org_items
    if len(memberships) > 1:
        return None, None, True, org_items
    return None, None, False, org_items


def _legacy_roles(db: Session, user_id: str) -> list[str]:
    rows = (
        db.query(Role.name)
        .join(UserRole, UserRole.role_id == Role.id)
        .filter(UserRole.user_id == user_id)
        .all()
    )
    return [str(row[0]) for row in rows]


def _resolve_platform_role(db: Session, user: User) -> str | None:
    if user.platform_role in VALID_PLATFORM_ROLES:
        return user.platform_role
    roles = _legacy_roles(db, user.id)
    if "platform_owner" in roles:
        return "platform_owner"
    if "platform_admin" in roles:
        return "platform_admin"
    return None


def _auth_payload(
    *,
    db: Session,
    settings,
    user: User,
    organization_id: str | None,
    org_role: str | None,
    auth_session: AuthSession,
    requires_org_selection: bool = False,
    organizations: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    platform_role = _resolve_platform_role(db, user)
    access_jti = str(uuid.uuid4())
    access_token = create_token(
        user_id=user.id,
        organization_id=organization_id,
        org_role=org_role,
        platform_role=platform_role,
        token_type="access",
        ttl_seconds=settings.jwt_access_ttl_seconds,
        session_id=auth_session.id,
        token_id=access_jti,
    )
    resolved_refresh = create_token(
        user_id=user.id,
        organization_id=organization_id,
        org_role=org_role,
        platform_role=platform_role,
        token_type="refresh",
        ttl_seconds=settings.jwt_refresh_ttl_seconds,
        session_id=auth_session.id,
        token_id=auth_session.refresh_jti,
    )
    roles: list[str] = []
    if platform_role:
        roles.append(platform_role)
    if org_role:
        roles.append(org_role)
    if org_role in {"org_owner", "org_admin"}:
        roles.append("tenant_admin")

    return {
        "access_token": None if requires_org_selection else access_token,
        "refresh_token": resolved_refresh,
        "token_type": "bearer",
        "expires_in": settings.jwt_access_ttl_seconds,
        "requires_org_selection": requires_org_selection,
        "organizations": organizations or [],
        "user": {
            "id": user.id,
            "tenant_id": organization_id,
            "organization_id": organization_id,
            "org_role": org_role,
            "platform_role": platform_role,
            "roles": roles,
        },
    }


def _expires_at(settings) -> datetime:  # noqa: ANN001
    return datetime.now(UTC) + timedelta(seconds=settings.jwt_refresh_ttl_seconds)


def _create_auth_session(
    db: Session,
    *,
    user: User,
    organization_id: str | None,
    settings,
) -> AuthSession:
    now = datetime.now(UTC)
    row = AuthSession(
        user_id=user.id,
        organization_id=organization_id,
        refresh_jti=str(uuid.uuid4()),
        status=AUTH_SESSION_ACTIVE,
        expires_at=now + timedelta(seconds=settings.jwt_refresh_ttl_seconds),
        created_at=now,
        last_seen_at=now,
    )
    db.add(row)
    db.flush()
    return row


def _rotate_auth_session(
    db: Session,
    *,
    auth_session: AuthSession | None,
    user: User,
    organization_id: str | None,
    settings,
) -> AuthSession:
    if auth_session is None:
        return _create_auth_session(
            db,
            user=user,
            organization_id=organization_id,
            settings=settings,
        )
    auth_session.organization_id = organization_id
    auth_session.refresh_jti = str(uuid.uuid4())
    auth_session.last_seen_at = datetime.now(UTC)
    auth_session.expires_at = _expires_at(settings)
    auth_session.status = AUTH_SESSION_ACTIVE
    auth_session.revoked_at = None
    db.flush()
    return auth_session


def _normalized_expiry(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _session_from_token_payload(
    db: Session,
    *,
    payload: dict[str, Any],
    user_id: str,
    require_refresh_jti: bool,
    lock: bool = False,
) -> AuthSession | None:
    session_id = payload.get("sid")
    if session_id is None:
        # Transitional support for tokens issued before revocable sessions shipped.
        return None
    if not isinstance(session_id, str):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")

    query = db.query(AuthSession).filter(AuthSession.id == session_id)
    if lock:
        query = query.with_for_update()
    auth_session = query.first()
    now = datetime.now(UTC)
    if (
        auth_session is None
        or auth_session.user_id != user_id
        or auth_session.status != AUTH_SESSION_ACTIVE
        or _normalized_expiry(auth_session.expires_at) <= now
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired or revoked")
    if require_refresh_jti:
        token_jti = payload.get("jti")
        if not isinstance(token_jti, str) or token_jti != auth_session.refresh_jti:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh session has already been rotated")
    token_org_id = payload.get("organization_id")
    if token_org_id != auth_session.organization_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid organization session")
    return auth_session


def validate_access_session(
    db: Session,
    *,
    payload: dict[str, Any],
    user_id: str,
) -> AuthSession | None:
    return _session_from_token_payload(
        db,
        payload=payload,
        user_id=user_id,
        require_refresh_jti=False,
    )


def _decode_refresh_session(
    db: Session,
    refresh_token: str,
) -> tuple[dict[str, Any], User, AuthSession | None]:
    payload = decode_token(refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user_id = payload.get("user_id") or payload.get("sub")
    if not isinstance(user_id, str):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not active")
    auth_session = _session_from_token_payload(
        db,
        payload=payload,
        user_id=user_id,
        require_refresh_jti=True,
        lock=True,
    )
    return payload, user, auth_session


def login(db: Session, email: str, password: str, organization_id: str | None = None) -> dict:
    user = db.query(User).filter(User.email == email).first()
    if user is None or not verify_password(password, user.hashed_password) or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    platform_role = _resolve_platform_role(db, user)
    if platform_role and platform_role not in VALID_PLATFORM_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid platform role configuration")
    memberships = _list_memberships(db, user.id)
    for membership in memberships:
        if membership.role not in VALID_ORG_ROLES:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid organization role configuration")
    selected_org_id, selected_org_role, requires_org_selection, org_items = _resolve_org_context(
        memberships,
        organization_id,
    )
    org_items = _organization_items(db, memberships)
    if platform_role is None and selected_org_id is None and not requires_org_selection:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organization context is required")

    settings = get_settings()
    auth_session = _create_auth_session(
        db,
        user=user,
        organization_id=selected_org_id,
        settings=settings,
    )
    payload = _auth_payload(
        db=db,
        settings=settings,
        user=user,
        organization_id=selected_org_id,
        org_role=selected_org_role,
        auth_session=auth_session,
        requires_org_selection=requires_org_selection,
        organizations=org_items,
    )
    db.commit()
    return payload


def refresh(db: Session, refresh_token: str) -> dict:
    payload, user, auth_session = _decode_refresh_session(db, refresh_token)

    token_org_id = payload.get("organization_id")
    token_org_role = payload.get("org_role")
    memberships = _list_memberships(db, user.id)
    if token_org_id is None and len(memberships) > 1:
        settings = get_settings()
        rotated_session = _rotate_auth_session(
            db,
            auth_session=auth_session,
            user=user,
            organization_id=None,
            settings=settings,
        )
        response_payload = _auth_payload(
            db=db,
            settings=settings,
            user=user,
            organization_id=None,
            org_role=None,
            auth_session=rotated_session,
            requires_org_selection=True,
            organizations=_organization_items(db, memberships),
        )
        db.commit()
        return response_payload
    if token_org_id is None and len(memberships) == 1:
        token_org_id = memberships[0].organization_id
        token_org_role = memberships[0].role
    if token_org_id is not None:
        membership = (
            db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.user_id == user.id,
                OrganizationMembership.organization_id == token_org_id,
                OrganizationMembership.status == "active",
            )
            .first()
        )
        if membership is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organization access denied")
        token_org_role = membership.role

    settings = get_settings()
    rotated_session = _rotate_auth_session(
        db,
        auth_session=auth_session,
        user=user,
        organization_id=token_org_id if isinstance(token_org_id, str) else None,
        settings=settings,
    )
    response_payload = _auth_payload(
        db=db,
        settings=settings,
        user=user,
        organization_id=token_org_id if isinstance(token_org_id, str) else None,
        org_role=token_org_role if isinstance(token_org_role, str) else None,
        auth_session=rotated_session,
    )
    db.commit()
    return response_payload


def select_organization(db: Session, refresh_token: str, organization_id: str) -> dict:
    _payload, user, auth_session = _decode_refresh_session(db, refresh_token)

    membership = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.status == "active",
        )
        .first()
    )
    if membership is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organization access denied")

    settings = get_settings()
    rotated_session = _rotate_auth_session(
        db,
        auth_session=auth_session,
        user=user,
        organization_id=membership.organization_id,
        settings=settings,
    )
    response_payload = _auth_payload(
        db=db,
        settings=settings,
        user=user,
        organization_id=membership.organization_id,
        org_role=membership.role,
        auth_session=rotated_session,
    )
    db.commit()
    return response_payload


def revoke_session_from_token(db: Session, token: str) -> bool:
    try:
        payload = decode_token(token)
    except HTTPException:
        return False
    user_id = payload.get("user_id") or payload.get("sub")
    session_id = payload.get("sid")
    if not isinstance(user_id, str) or not isinstance(session_id, str):
        return False
    row = (
        db.query(AuthSession)
        .filter(
            AuthSession.id == session_id,
            AuthSession.user_id == user_id,
            AuthSession.status == AUTH_SESSION_ACTIVE,
        )
        .first()
    )
    if row is None:
        return False
    row.status = AUTH_SESSION_REVOKED
    row.revoked_at = datetime.now(UTC)
    db.commit()
    return True


def list_active_sessions(db: Session, *, user_id: str) -> list[dict[str, Any]]:
    now = datetime.now(UTC)
    rows = (
        db.query(AuthSession)
        .filter(
            AuthSession.user_id == user_id,
            AuthSession.status == AUTH_SESSION_ACTIVE,
            AuthSession.expires_at > now,
        )
        .order_by(AuthSession.last_seen_at.desc(), AuthSession.created_at.desc())
        .all()
    )
    return [
        {
            "id": row.id,
            "organization_id": row.organization_id,
            "status": row.status,
            "created_at": row.created_at,
            "last_seen_at": row.last_seen_at,
            "expires_at": row.expires_at,
        }
        for row in rows
    ]


def revoke_user_session(
    db: Session,
    *,
    user_id: str,
    session_id: str,
) -> bool:
    row = (
        db.query(AuthSession)
        .filter(
            AuthSession.id == session_id,
            AuthSession.user_id == user_id,
            AuthSession.status == AUTH_SESSION_ACTIVE,
        )
        .first()
    )
    if row is None:
        return False
    row.status = AUTH_SESSION_REVOKED
    row.revoked_at = datetime.now(UTC)
    db.commit()
    return True
