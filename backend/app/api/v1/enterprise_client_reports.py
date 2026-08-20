from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import require_exact_org_role
from app.api.response import envelope
from app.db.session import get_db
from app.services import enterprise_client_report_service
from app.services.cost_economics_service import CostEconomicsError


router = APIRouter(prefix="/enterprise/client-reports", tags=["enterprise-client-reports"])
client_report_user = require_exact_org_role({"org_client"})


@router.get("")
def get_client_reports(
    request: Request,
    user: dict = Depends(client_report_user),
    db: Session = Depends(get_db),
) -> dict:
    try:
        payload = enterprise_client_report_service.list_client_reports(
            db,
            tenant_id=str(user["tenant_id"]),
            organization_id=str(user["organization_id"]),
            user_id=str(user["id"]),
        )
    except (enterprise_client_report_service.EnterpriseClientReportError, CostEconomicsError) as exc:
        _raise_client_report_error(exc)
    return envelope(request, payload)


@router.get("/{report_id}/view")
def get_client_report_view(
    report_id: str,
    user: dict = Depends(client_report_user),
    db: Session = Depends(get_db),
) -> Response:
    try:
        content = enterprise_client_report_service.read_client_report_html(
            db,
            tenant_id=str(user["tenant_id"]),
            organization_id=str(user["organization_id"]),
            user_id=str(user["id"]),
            report_id=report_id,
        )
        db.commit()
    except (enterprise_client_report_service.EnterpriseClientReportError, CostEconomicsError) as exc:
        db.rollback()
        _raise_client_report_error(exc)
    return Response(
        content=content,
        media_type="text/html; charset=utf-8",
        headers={
            "Cache-Control": "private, no-store",
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src data:",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
            "X-Robots-Tag": "noindex, nofollow",
        },
    )


def _raise_client_report_error(exc: Exception) -> None:
    raise HTTPException(
        status_code=int(getattr(exc, "status_code", 400)),
        detail={
            "message": str(exc),
            "reason_code": str(getattr(exc, "reason_code", "client_report_failed")),
        },
    ) from exc
