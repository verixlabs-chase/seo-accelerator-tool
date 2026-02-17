from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.response import envelope
from app.db.session import get_db
from app.schemas.reporting import ReportDeliverIn, ReportGenerateIn, ReportOut
from app.services import reporting_service
from app.tasks.tasks import reporting_aggregate_kpis, reporting_freeze_window, reporting_render_html, reporting_render_pdf, reporting_send_email

router = APIRouter(prefix="/reports", tags=["reports"])


def _dispatch_report_generate(tenant_id: str, campaign_id: str, month_number: int, report_id: str) -> None:
    try:
        reporting_freeze_window.delay(tenant_id=tenant_id, campaign_id=campaign_id, month_number=month_number)
        reporting_aggregate_kpis.delay(tenant_id=tenant_id, campaign_id=campaign_id, month_number=month_number)
        reporting_render_html.delay(tenant_id=tenant_id, report_id=report_id)
        reporting_render_pdf.delay(tenant_id=tenant_id, report_id=report_id)
    except Exception:
        return


def _dispatch_report_delivery(tenant_id: str, report_id: str, recipient: str) -> None:
    try:
        reporting_send_email.delay(tenant_id=tenant_id, report_id=report_id, recipient=recipient)
    except Exception:
        return


@router.post("/generate")
def generate_report(
    request: Request,
    background_tasks: BackgroundTasks,
    body: ReportGenerateIn,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    report = reporting_service.generate_report(
        db,
        tenant_id=user["tenant_id"],
        campaign_id=body.campaign_id,
        month_number=body.month_number,
    )
    background_tasks.add_task(_dispatch_report_generate, user["tenant_id"], body.campaign_id, body.month_number, report.id)
    return envelope(request, ReportOut.model_validate(report).model_dump(mode="json"))


@router.get("")
def list_reports(
    request: Request,
    campaign_id: str | None = Query(default=None),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    rows = reporting_service.list_reports(db, tenant_id=user["tenant_id"], campaign_id=campaign_id)
    return envelope(request, {"items": [ReportOut.model_validate(r).model_dump(mode="json") for r in rows]})


@router.get("/{report_id}")
def get_report(
    request: Request,
    report_id: str,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    row = reporting_service.get_report(db, tenant_id=user["tenant_id"], report_id=report_id)
    artifacts = reporting_service.get_report_artifacts(db, tenant_id=user["tenant_id"], report_id=report_id)
    return envelope(
        request,
        {
            "report": ReportOut.model_validate(row).model_dump(mode="json"),
            "artifacts": [
                {"id": a.id, "artifact_type": a.artifact_type, "storage_path": a.storage_path, "created_at": a.created_at.isoformat()}
                for a in artifacts
            ],
        },
    )


@router.post("/{report_id}/deliver")
def deliver_report(
    request: Request,
    background_tasks: BackgroundTasks,
    report_id: str,
    body: ReportDeliverIn,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    payload = reporting_service.deliver_report(db, tenant_id=user["tenant_id"], report_id=report_id, recipient=body.recipient)
    background_tasks.add_task(_dispatch_report_delivery, user["tenant_id"], report_id, body.recipient)
    return envelope(request, payload)
