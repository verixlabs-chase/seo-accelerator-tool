from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from fastapi import HTTPException, status

from app.core.config import get_settings


def create_token(
    *,
    user_id: str,
    organization_id: str | None,
    org_role: str | None,
    platform_role: str | None,
    token_type: str,
    ttl_seconds: int,
) -> str:
    now = datetime.now(UTC)
    legacy_roles: list[str] = []
    if platform_role:
        legacy_roles.append(platform_role)
    if org_role:
        legacy_roles.append(org_role)
        if org_role in {"org_owner", "org_admin"}:
            legacy_roles.append("tenant_admin")
    payload: dict[str, Any] = {
        "sub": user_id,
        "user_id": user_id,
        "tenant_id": organization_id,
        "organization_id": organization_id,
        "org_role": org_role,
        "platform_role": platform_role,
        "roles": legacy_roles,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl_seconds)).timestamp()),
    }
    settings = get_settings()
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
