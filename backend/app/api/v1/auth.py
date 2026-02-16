from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.response import envelope
from app.db.session import get_db
from app.schemas.auth import LoginRequest, RefreshRequest
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
def login(request: Request, body: LoginRequest, db: Session = Depends(get_db)) -> dict:
    payload = auth_service.login(db, body.email, body.password)
    request.state.tenant_id = payload["user"]["tenant_id"]
    return envelope(request, payload)


@router.post("/refresh")
def refresh(request: Request, body: RefreshRequest, db: Session = Depends(get_db)) -> dict:
    payload = auth_service.refresh(db, body.refresh_token)
    request.state.tenant_id = payload["user"]["tenant_id"]
    return envelope(request, payload)


@router.get("/me")
def me(request: Request, user: dict = Depends(get_current_user)) -> dict:
    return envelope(request, user)

