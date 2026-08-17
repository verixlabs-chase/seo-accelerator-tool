from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import require_org_role
from app.api.response import envelope
from app.db.session import get_db
from app.models.organization import Organization
from app.services import stripe_billing_service


router = APIRouter(prefix="/billing", tags=["billing"])


class CheckoutIn(BaseModel):
    plan_code: str = Field(..., pattern="^(solo|standard|growth|multi_location)$")
    client_request_id: str = Field(
        ...,
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$",
    )


def _organization(db: Session, user: dict) -> Organization:
    organization = db.get(Organization, user["organization_id"])
    if organization is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return organization


def _http_error(exc: stripe_billing_service.BillingError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={"message": str(exc), "reason_code": exc.reason_code},
    )


@router.get("/summary")
def billing_summary(
    request: Request,
    user: dict = Depends(require_org_role({"org_user"})),
    db: Session = Depends(get_db),
) -> dict:
    return envelope(request, stripe_billing_service.get_billing_summary(_organization(db, user)))


@router.get("/readiness")
def billing_readiness(
    request: Request,
    user: dict = Depends(require_org_role({"org_user"})),
    db: Session = Depends(get_db),
) -> dict:
    return envelope(
        request,
        stripe_billing_service.get_billing_readiness(_organization(db, user)),
    )


@router.post("/checkout")
def create_checkout(
    request: Request,
    body: CheckoutIn,
    user: dict = Depends(require_org_role({"org_owner"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        result = stripe_billing_service.create_checkout_session(
            db,
            organization=_organization(db, user),
            requested_plan_code=body.plan_code,
            client_request_id=body.client_request_id,
            actor_user_id=user["id"],
        )
        db.commit()
    except stripe_billing_service.BillingError as exc:
        db.rollback()
        raise _http_error(exc) from exc
    return envelope(request, result)


@router.post("/portal")
def create_portal(
    request: Request,
    user: dict = Depends(require_org_role({"org_owner"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        result = stripe_billing_service.create_customer_portal_session(
            db,
            organization=_organization(db, user),
            actor_user_id=user["id"],
        )
        db.commit()
    except stripe_billing_service.BillingError as exc:
        db.rollback()
        raise _http_error(exc) from exc
    return envelope(request, result)


@router.post("/webhook")
async def billing_webhook(
    request: Request,
    stripe_signature: str = Header(default="", alias="Stripe-Signature"),
    db: Session = Depends(get_db),
) -> dict:
    raw_body = await request.body()
    try:
        result = stripe_billing_service.process_webhook(
            db,
            raw_body=raw_body,
            signature_header=stripe_signature,
        )
    except stripe_billing_service.BillingError as exc:
        raise _http_error(exc) from exc
    return envelope(request, result)
