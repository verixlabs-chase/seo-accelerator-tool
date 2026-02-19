import uuid
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.passwords import hash_password, verify_password
from app.core.security import create_token, decode_token
from app.models.organization import Organization
from app.models.organization_membership import OrganizationMembership
from app.models.role import Role, UserRole
from app.models.tenant import Tenant
from app.models.user import User


VALID_PLATFORM_ROLES = {"platform_owner", "platform_admin"}
VALID_ORG_ROLES = {"org_owner", "org_admin", "org_user"}


def seed_local_admin(db: Session) -> None:
    tenant = db.query(Tenant).filter(Tenant.name == "Default Tenant").first()
    if tenant is None:
        tenant = Tenant(name="Default Tenant")
        db.add(tenant)
        db.flush()

    organization = db.query(Organization).filter(Organization.id == tenant.id).first()
    if organization is None:
        organization = Organization(
            id=tenant.id,
            name=f"default-org-{tenant.id[:8]}",
            plan_type="standard",
            billing_mode="subscription",
            status="active",
        )
        db.add(organization)
        db.flush()

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


def _list_memberships(db: Session, user_id: str) -> list[OrganizationMembership]:
    return (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.status == "active",
        )
        .all()
    )


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
    refresh_token: str | None = None,
    requires_org_selection: bool = False,
    organizations: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    platform_role = _resolve_platform_role(db, user)
    access_token = create_token(
        user_id=user.id,
        organization_id=organization_id,
        org_role=org_role,
        platform_role=platform_role,
        token_type="access",
        ttl_seconds=settings.jwt_access_ttl_seconds,
    )
    resolved_refresh = refresh_token or create_token(
        user_id=user.id,
        organization_id=organization_id,
        org_role=org_role,
        platform_role=platform_role,
        token_type="refresh",
        ttl_seconds=settings.jwt_refresh_ttl_seconds,
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
    if platform_role is None and selected_org_id is None and not requires_org_selection:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organization context is required")

    settings = get_settings()
    refresh_token = create_token(
        user_id=user.id,
        organization_id=selected_org_id,
        org_role=selected_org_role,
        platform_role=platform_role,
        token_type="refresh",
        ttl_seconds=settings.jwt_refresh_ttl_seconds,
    )
    return _auth_payload(
        db=db,
        settings=settings,
        user=user,
        organization_id=selected_org_id,
        org_role=selected_org_role,
        refresh_token=refresh_token,
        requires_org_selection=requires_org_selection,
        organizations=org_items,
    )


def refresh(db: Session, refresh_token: str) -> dict:
    payload = decode_token(refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user_id = payload.get("user_id") or payload.get("sub")
    if not isinstance(user_id, str):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not active")

    token_org_id = payload.get("organization_id")
    token_org_role = payload.get("org_role")
    memberships = _list_memberships(db, user.id)
    if token_org_id is None and len(memberships) > 1:
        settings = get_settings()
        return _auth_payload(
            db=db,
            settings=settings,
            user=user,
            organization_id=None,
            org_role=None,
            refresh_token=refresh_token,
            requires_org_selection=True,
            organizations=[{"organization_id": row.organization_id, "role": row.role} for row in memberships],
        )
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
    return _auth_payload(
        db=db,
        settings=settings,
        user=user,
        organization_id=token_org_id if isinstance(token_org_id, str) else None,
        org_role=token_org_role if isinstance(token_org_role, str) else None,
        refresh_token=refresh_token,
    )


def select_organization(db: Session, refresh_token: str, organization_id: str) -> dict:
    payload = decode_token(refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    user_id = payload.get("user_id") or payload.get("sub")
    if not isinstance(user_id, str):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not active")

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
    return _auth_payload(
        db=db,
        settings=settings,
        user=user,
        organization_id=membership.organization_id,
        org_role=membership.role,
    )
