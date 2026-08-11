from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import require_org_role, require_platform_role
from app.api.response import envelope
from app.db.session import get_db
from app.schemas.product_analytics import ProductEventCreateIn, ProductFeedbackCreateIn
from app.services import product_analytics_service


tenant_router = APIRouter(prefix="/product-analytics", tags=["product-analytics"])
control_plane_router = APIRouter(prefix="/platform/product-value", tags=["platform-product-value"])


def _translate_error(exc: product_analytics_service.ProductAnalyticsError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={"message": str(exc), "reason_code": exc.reason_code},
    )


@tenant_router.post("/events")
def create_product_event(
    request: Request,
    body: ProductEventCreateIn,
    user: dict = Depends(require_org_role({"org_user"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        row, created = product_analytics_service.record_event(
            db,
            tenant_id=user["tenant_id"],
            organization_id=user["organization_id"],
            actor_user_id=user["id"],
            event_name=body.event_name,
            campaign_id=body.campaign_id,
            properties=body.properties,
            occurred_at=body.occurred_at,
            idempotency_key=body.idempotency_key,
        )
    except product_analytics_service.ProductAnalyticsError as exc:
        raise _translate_error(exc) from exc
    db.commit()
    db.refresh(row)
    return envelope(
        request,
        {
            "event": product_analytics_service.serialize_event(row),
            "created": created,
        },
    )


@tenant_router.post("/feedback")
def create_product_feedback(
    request: Request,
    body: ProductFeedbackCreateIn,
    user: dict = Depends(require_org_role({"org_user"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        row = product_analytics_service.record_feedback(
            db,
            tenant_id=user["tenant_id"],
            organization_id=user["organization_id"],
            actor_user_id=user["id"],
            campaign_id=body.campaign_id,
            context=body.context,
            subject_type=body.subject_type,
            subject_id=body.subject_id,
            rating=body.rating,
            reason_code=body.reason_code,
        )
    except product_analytics_service.ProductAnalyticsError as exc:
        raise _translate_error(exc) from exc
    db.commit()
    return envelope(
        request,
        {
            "feedback": {
                "id": row.id,
                "context": row.context,
                "rating": row.rating,
                "saved": True,
            }
        },
    )


@control_plane_router.get("/summary")
def get_product_value_summary(
    request: Request,
    days: int = Query(default=30, ge=7, le=180),
    _user: dict = Depends(require_platform_role({"platform_owner", "platform_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    return envelope(request, product_analytics_service.build_value_summary(db, days=days))


@control_plane_router.get("/taxonomy")
def get_product_event_taxonomy(
    request: Request,
    _user: dict = Depends(require_platform_role({"platform_owner", "platform_admin"})),
) -> dict:
    return envelope(request, product_analytics_service.taxonomy_summary())
