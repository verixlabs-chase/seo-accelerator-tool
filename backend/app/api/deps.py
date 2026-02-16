from collections.abc import Callable

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.db.session import get_db
from app.models.role import Role, UserRole
from app.models.user import User


def get_current_user(
    request: Request,
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
) -> dict:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = authorization.replace("Bearer ", "", 1).strip()
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    user = db.get(User, payload["sub"])
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not active")
    if payload.get("tenant_id") != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Tenant mismatch")

    roles = (
        db.query(Role.name)
        .join(UserRole, UserRole.role_id == Role.id)
        .filter(UserRole.user_id == user.id)
        .all()
    )
    request.state.tenant_id = payload["tenant_id"]
    return {"id": user.id, "tenant_id": payload["tenant_id"], "roles": [row[0] for row in roles]}


def require_roles(required: set[str]) -> Callable:
    def _enforcer(user: dict = Depends(get_current_user)) -> dict:
        user_roles = set(user["roles"])
        if user_roles.isdisjoint(required):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user

    return _enforcer
