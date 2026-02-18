import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.passwords import hash_password, verify_password
from app.core.security import create_token, decode_token
from app.models.role import Role, UserRole
from app.models.tenant import Tenant
from app.models.user import User


def seed_local_admin(db: Session) -> None:
    tenant = db.query(Tenant).filter(Tenant.name == "Default Tenant").first()
    if tenant is None:
        tenant = Tenant(name="Default Tenant")
        db.add(tenant)
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
        user = User(tenant_id=tenant.id, email="admin@local.dev", password_hash=hash_password("admin123!"))
        db.add(user)
        db.flush()
        db.add(UserRole(id=str(uuid.uuid4()), user_id=user.id, role_id=role.id))
        db.add(UserRole(id=str(uuid.uuid4()), user_id=user.id, role_id=platform_role.id))
        db.commit()


def _get_roles(db: Session, user_id: str) -> list[str]:
    rows = (
        db.query(Role.name)
        .join(UserRole, UserRole.role_id == Role.id)
        .filter(UserRole.user_id == user_id)
        .all()
    )
    return [row[0] for row in rows]


def login(db: Session, email: str, password: str) -> dict:
    user = db.query(User).filter(User.email == email).first()
    if user is None or not verify_password(password, user.password_hash) or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    settings = get_settings()
    roles = _get_roles(db, user.id)
    access_token = create_token(
        subject=user.id,
        tenant_id=user.tenant_id,
        roles=roles,
        token_type="access",
        ttl_seconds=settings.jwt_access_ttl_seconds,
    )
    refresh_token = create_token(
        subject=user.id,
        tenant_id=user.tenant_id,
        roles=roles,
        token_type="refresh",
        ttl_seconds=settings.jwt_refresh_ttl_seconds,
    )
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.jwt_access_ttl_seconds,
        "user": {"id": user.id, "tenant_id": user.tenant_id, "roles": roles},
    }


def refresh(db: Session, refresh_token: str) -> dict:
    payload = decode_token(refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user = db.get(User, payload["sub"])
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not active")

    settings = get_settings()
    access_token = create_token(
        subject=user.id,
        tenant_id=user.tenant_id,
        roles=payload.get("roles", []),
        token_type="access",
        ttl_seconds=settings.jwt_access_ttl_seconds,
    )
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.jwt_access_ttl_seconds,
        "user": {"id": user.id, "tenant_id": user.tenant_id, "roles": payload.get("roles", [])},
    }
