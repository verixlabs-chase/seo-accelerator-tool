from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import ACCESS_TOKEN_COOKIE_NAME, decode_token
from app.db.session import get_db, set_session_security_context
from app.models.organization_membership import OrganizationMembership
from app.models.organization import Organization
from app.models.user import User
from app.services import auth_service


_PLATFORM_ROLE_ORDER = {"platform_admin": 1, "platform_owner": 2}
_ORG_ROLE_ORDER = {"org_user": 1, "org_admin": 2, "org_owner": 3}
_LEGACY_TO_ORG_ROLE = {"tenant_admin": "org_admin"}
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def _effective_roles(org_role: str | None, platform_role: str | None) -> list[str]:
    roles: list[str] = []
    if platform_role:
        roles.append(platform_role)
    if org_role:
        roles.append(org_role)
        if org_role in {"org_owner", "org_admin"}:
            roles.append("tenant_admin")
    return roles


def get_current_user(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> dict:
    if token is None:
        token = request.cookies.get(ACCESS_TOKEN_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authentication session")
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    user_id = payload.get("user_id") or payload.get("sub")
    if not isinstance(user_id, str):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject")
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not active")
    auth_service.validate_access_session(db, payload=payload, user_id=user_id)

    organization_id = payload.get("organization_id")
    if organization_id is None and isinstance(payload.get("tenant_id"), str):
        organization_id = payload.get("tenant_id")
    org_role = payload.get("org_role")
    if isinstance(org_role, str):
        org_role = _LEGACY_TO_ORG_ROLE.get(org_role, org_role)
    platform_role = payload.get("platform_role")
    if platform_role is not None and platform_role not in _PLATFORM_ROLE_ORDER:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid platform role context")

    if organization_id is not None:
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
        if org_role is None:
            org_role = membership.role
        elif membership.role != org_role:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid organization role context")

        organization = db.get(Organization, organization_id)
        if organization is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organization access denied")
        if organization.status in {"closure_pending", "closed"}:
            safe_method = request.method.upper() in {"GET", "HEAD", "OPTIONS"}
            governance_recovery_path = (
                f"/organizations/{organization_id}/data-governance/closures" in request.url.path
                or f"/organizations/{organization_id}/data-governance/exports" in request.url.path
            )
            logout_path = request.url.path.endswith("/auth/logout")
            if not safe_method and not governance_recovery_path and not logout_path:
                raise HTTPException(
                    status_code=status.HTTP_423_LOCKED,
                    detail={
                        "message": (
                            "This workspace is read-only while closure is pending. "
                            "An account owner can reopen it during the recovery window."
                        ),
                        "reason_code": "organization_closure_read_only",
                    },
                )

    request.state.tenant_id = organization_id
    request.state.organization_id = organization_id
    set_session_security_context(
        db,
        tenant_id=organization_id,
        organization_id=organization_id,
        user_id=user.id,
        platform_access=isinstance(platform_role, str),
    )
    return {
        "id": user.id,
        "user_id": user.id,
        "tenant_id": organization_id,
        "organization_id": organization_id,
        "org_role": org_role,
        "organization_status": organization.status if organization_id is not None else None,
        "platform_role": platform_role,
        "is_platform_user": user.is_platform_user,
        "roles": _effective_roles(org_role, platform_role),
    }


def require_platform_role(required: set[str]) -> Callable:
    def _enforcer(user: dict = Depends(get_current_user)) -> dict:
        role = user.get("platform_role")
        if not isinstance(role, str):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Platform role required")
        role_level = _PLATFORM_ROLE_ORDER.get(role, 0)
        required_level = min(_PLATFORM_ROLE_ORDER.get(item, 0) for item in required)
        if role_level < required_level:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient platform role")
        return user

    return _enforcer


def require_platform_owner() -> Callable:
    def _enforcer(user: dict = Depends(get_current_user)) -> dict:
        if user.get("platform_role") != "platform_owner":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Platform owner role required")
        return user

    return _enforcer


def require_org_role(required: set[str]) -> Callable:
    resolved_required = {_LEGACY_TO_ORG_ROLE.get(item, item) for item in required}

    def _enforcer(user: dict = Depends(get_current_user)) -> dict:
        if user.get("organization_id") is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organization context required")
        role = user.get("org_role")
        if not isinstance(role, str):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organization role required")
        role_level = _ORG_ROLE_ORDER.get(role, 0)
        required_level = min(_ORG_ROLE_ORDER.get(item, 0) for item in resolved_required)
        if role_level < required_level:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient organization role")
        return user

    return _enforcer


def require_roles(required: set[str]) -> Callable:
    required_org = {_LEGACY_TO_ORG_ROLE.get(item, item) for item in required if item in _ORG_ROLE_ORDER or item in _LEGACY_TO_ORG_ROLE}
    required_platform = {item for item in required if item in _PLATFORM_ROLE_ORDER}

    def _enforcer(user: dict = Depends(get_current_user)) -> dict:
        platform_ok = False
        org_ok = False
        if required_platform:
            role = user.get("platform_role")
            role_level = _PLATFORM_ROLE_ORDER.get(str(role), 0)
            platform_ok = role_level >= min(_PLATFORM_ROLE_ORDER[item] for item in required_platform)
        else:
            platform_ok = True
        if required_org:
            if user.get("organization_id") is None:
                org_ok = False
            else:
                role = user.get("org_role")
                role_level = _ORG_ROLE_ORDER.get(str(role), 0)
                org_ok = role_level >= min(_ORG_ROLE_ORDER[item] for item in required_org)
        else:
            org_ok = True
        if required_platform and required_org:
            allowed = platform_ok or org_ok
        elif required_platform:
            allowed = platform_ok
        elif required_org:
            allowed = org_ok
        else:
            allowed = True
        if not allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user

    return _enforcer


def enforce_organization_scope(
    *,
    user: dict,
    organization_id: str,
    allow_platform: bool = True,
) -> None:
    if allow_platform and isinstance(user.get("platform_role"), str):
        return
    if user.get("organization_id") != organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "message": "Organization context does not match request scope.",
                "reason_code": "organization_scope_mismatch",
            },
        )
