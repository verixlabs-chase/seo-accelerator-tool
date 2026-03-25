from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.response import envelope
from app.db.session import get_db
from app.providers import get_email_adapter
from app.schemas.reporting import ReportArtifactOut, ReportDeliverIn, ReportDeliveryEventOut, ReportGenerateIn, ReportOut, ReportScheduleOut, ReportScheduleUpsertIn
from app.services import reporting_service
from app.services.runtime_truth_service import build_truth, freshness_state_from_timestamp
from app.tasks.tasks import (
    reporting_aggregate_kpis,
    reporting_freeze_window,
    reporting_process_schedule,
    reporting_render_html,
    reporting_render_pdf,
    reporting_send_email,
)

router = APIRouter(prefix="/reports", tags=["reports"])


def _report_truth(
    *,
    report_count: int,
    report_status: str | None = None,
    artifacts: list[dict] | None = None,
    delivery_events: list[dict] | None = None,
    delivery_status: str | None = None,
    generated_at: str | None = None,
) -> dict:
    adapter_name = type(get_email_adapter()).__name__.lower()
    states: list[str] = []
    reasons: list[str] = []

    artifacts = artifacts or []
    delivery_events = delivery_events or []
    ready_artifacts = [artifact for artifact in artifacts if artifact.get("ready")]
    has_synthetic_delivery = "synthetic" in adapter_name
    normalized_report_status = (report_status or "").lower()
    normalized_delivery_status = (delivery_status or "").lower()
    event_statuses = {(event.get("delivery_status") or "").lower() for event in delivery_events}

    if has_synthetic_delivery:
        states.append("synthetic")
        states.append("delivery_unverified")
        reasons.append("report_delivery_uses_synthetic_email_adapter")
    if report_count == 0:
        states.append("unavailable")
        reasons.append("no_report_generated_yet")
    if report_count > 0:
        states.append("generated")
    if normalized_report_status in {"queued", "pending", "running", "in_progress", "scheduled", "processing"}:
        states.append("in_progress")
        reasons.append("report_record_exists_but_generation_is_not_complete")
    if artifacts:
        states.append("minimal_artifact")
        states.append("non_durable")
        states.append("operator_assisted")
        reasons.append("report_artifacts_are_minimal_local_files")
        reasons.append("report_artifacts_are_local_disk_and_not_durable")
    if artifacts and not ready_artifacts:
        states.append("in_progress")
        reasons.append("report_artifacts_are_not_ready")
    if normalized_report_status == "delivered" and not delivery_events:
        states.append("delivery_unverified")
        reasons.append("report_marked_delivered_without_event_level_confirmation")
    if "sent" in event_statuses or normalized_delivery_status == "sent":
        states.append("delivery_unverified")
        reasons.append("report_delivery_marked_sent_without_external_verification")
    if event_statuses.intersection({"queued", "pending", "running", "in_progress", "processing", "deferred"}) or normalized_delivery_status in {
        "queued",
        "pending",
        "running",
        "in_progress",
        "processing",
        "deferred",
    }:
        states.append("in_progress")
        reasons.append("report_delivery_is_not_finished")

    freshness_state = freshness_state_from_timestamp(generated_at, stale_after=timedelta(days=31))
    if freshness_state == "stale":
        states.append("stale")
        reasons.append("report_snapshot_is_stale")

    summary_parts = ["Reports are generated from stored campaign data, not from a premium reporting pipeline."]
    if report_count > 0:
        summary_parts.append("A generated report record only confirms that a summary was assembled.")
    if artifacts:
        summary_parts.append("Artifacts are minimal local HTML/PDF files stored on local disk.")
        summary_parts.append("These files are not durable or remotely retrievable.")
    if has_synthetic_delivery:
        summary_parts.append("Delivery confirmation is synthetic in this runtime, so 'sent' does not prove external email delivery.")
    elif normalized_report_status == "delivered" or "sent" in event_statuses or normalized_delivery_status == "sent":
        summary_parts.append("Delivery state is application-level only and should be confirmed separately before treating it as inbox delivery.")
    if normalized_report_status in {"queued", "pending", "running", "in_progress", "scheduled", "processing"}:
        summary_parts.append("This report is still being prepared and should not be treated as complete.")

    return build_truth(
        states=states or ["operator_assisted"],
        summary=" ".join(summary_parts),
        provider_state="local_disk_artifacts",
        setup_state="configured",
        operator_state="operator_review_required",
        freshness_state=freshness_state,
        reasons=reasons,
    )


def _schedule_truth(schedule: dict | None) -> dict:
    if schedule is None:
        return build_truth(
            states=["unavailable"],
            summary="No recurring report schedule exists yet. Automatic generation and delivery are not configured.",
            provider_state="scheduler_record",
            setup_state="missing",
            operator_state="manual_schedule_required",
            reasons=["no_report_schedule_configured"],
        )

    status = (schedule.get("last_status") or "").lower()
    enabled = bool(schedule.get("enabled"))
    next_run_at = schedule.get("next_run_at")
    states: list[str] = ["operator_assisted"]
    reasons: list[str] = ["report_schedule_requires_operator_monitoring"]
    freshness_state = "unknown"

    if enabled and status == "scheduled":
        states.append("scheduled")
        reasons.append("report_schedule_exists")
    if status == "retry_pending":
        states.append("in_progress")
        reasons.append("report_schedule_retry_in_progress")
    if not enabled or status in {"disabled", "max_retries_exceeded"}:
        states.append("unavailable")
        reasons.append("report_schedule_is_not_dependable")

    if next_run_at:
        try:
            next_run_dt = datetime.fromisoformat(str(next_run_at).replace("Z", "+00:00"))
            if next_run_dt.tzinfo is None:
                next_run_dt = next_run_dt.replace(tzinfo=UTC)
            else:
                next_run_dt = next_run_dt.astimezone(UTC)
            if enabled and next_run_dt < datetime.now(UTC) - timedelta(hours=1):
                states.append("stale")
                freshness_state = "stale"
                reasons.append("report_schedule_next_run_is_past_due")
            else:
                freshness_state = "current"
        except ValueError:
            freshness_state = "unknown"

    summary_parts = [
        "A report schedule only means automatic generation is configured.",
        "It does not prove that a report was generated, stored durably, or delivered successfully.",
    ]
    if status == "scheduled" and enabled:
        summary_parts.append("The scheduler is active for the next configured run.")
    elif status == "retry_pending":
        summary_parts.append("The scheduler is retrying a recent run and is not stable yet.")
    elif not enabled or status in {"disabled", "max_retries_exceeded"}:
        summary_parts.append("The scheduler is paused or not dependable in its current state.")

    return build_truth(
        states=states,
        summary=" ".join(summary_parts),
        provider_state="scheduler_record",
        setup_state="configured" if enabled else "paused",
        operator_state="operator_review_required",
        freshness_state=freshness_state,
        reasons=reasons,
    )


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


def _dispatch_report_schedule(tenant_id: str, campaign_id: str) -> None:
    try:
        if bool(getattr(getattr(reporting_process_schedule, "app", None), "conf", None) and reporting_process_schedule.app.conf.task_always_eager):
            return
        reporting_process_schedule.delay(tenant_id=tenant_id, campaign_id=campaign_id)
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
        organization_id=user["organization_id"],
    )
    background_tasks.add_task(_dispatch_report_generate, user["tenant_id"], body.campaign_id, body.month_number, report.id)
    payload = ReportOut.model_validate(report).model_dump(mode="json")
    return envelope(
        request,
        {
            **payload,
            "truth": _report_truth(report_count=1, report_status=payload.get("report_status"), generated_at=payload.get("generated_at")),
        },
    )


@router.get("")
def list_reports(
    request: Request,
    campaign_id: str | None = Query(default=None),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    rows = reporting_service.list_reports(
        db,
        tenant_id=user["tenant_id"],
        campaign_id=campaign_id,
        organization_id=user["organization_id"],
    )
    items = [ReportOut.model_validate(r).model_dump(mode="json") for r in rows]
    return envelope(
        request,
        {
            "items": items,
            "truth": _report_truth(
                report_count=len(items),
                report_status=items[0].get("report_status") if items else None,
                generated_at=items[0].get("generated_at") if items else None,
            ),
        },
    )


@router.get("/schedule")
def get_report_schedule(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    schedule = reporting_service.get_report_schedule(
        db,
        tenant_id=user["tenant_id"],
        campaign_id=campaign_id,
        organization_id=user["organization_id"],
    )
    if schedule is None:
        return envelope(request, None)
    payload = ReportScheduleOut.model_validate(schedule).model_dump(mode="json")
    return envelope(request, {**payload, "truth": _schedule_truth(payload)})


@router.put("/schedule")
def put_report_schedule(
    request: Request,
    background_tasks: BackgroundTasks,
    body: ReportScheduleUpsertIn,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    schedule = reporting_service.upsert_report_schedule(
        db,
        tenant_id=user["tenant_id"],
        campaign_id=body.campaign_id,
        cadence=body.cadence,
        timezone=body.timezone,
        next_run_at=body.next_run_at,
        enabled=body.enabled,
        organization_id=user["organization_id"],
    )
    background_tasks.add_task(_dispatch_report_schedule, user["tenant_id"], body.campaign_id)
    payload = ReportScheduleOut.model_validate(schedule).model_dump(mode="json")
    return envelope(request, {**payload, "truth": _schedule_truth(payload)})


@router.get("/{report_id}")
def get_report(
    request: Request,
    report_id: str,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    row = reporting_service.get_report(
        db,
        tenant_id=user["tenant_id"],
        report_id=report_id,
        organization_id=user["organization_id"],
    )
    artifacts = reporting_service.get_report_artifacts(
        db,
        tenant_id=user["tenant_id"],
        report_id=report_id,
        organization_id=user["organization_id"],
    )
    delivery_events = reporting_service.get_report_deliveries(
        db,
        tenant_id=user["tenant_id"],
        report_id=report_id,
        organization_id=user["organization_id"],
    )
    return envelope(
        request,
        {
            "report": ReportOut.model_validate(row).model_dump(mode="json"),
            "artifacts": [
                ReportArtifactOut.model_validate(reporting_service.artifact_contract(a)).model_dump(mode="json")
                for a in artifacts
            ],
            "delivery_events": [ReportDeliveryEventOut.model_validate(e).model_dump(mode="json") for e in delivery_events],
            "truth": _report_truth(
                report_count=1,
                report_status=row.report_status,
                artifacts=[
                    ReportArtifactOut.model_validate(reporting_service.artifact_contract(a)).model_dump(mode="json")
                    for a in artifacts
                ],
                delivery_events=[ReportDeliveryEventOut.model_validate(e).model_dump(mode="json") for e in delivery_events],
                generated_at=row.generated_at.isoformat() if row.generated_at else None,
            ),
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
    payload = reporting_service.deliver_report(
        db,
        tenant_id=user["tenant_id"],
        report_id=report_id,
        recipient=body.recipient,
        organization_id=user["organization_id"],
    )
    background_tasks.add_task(_dispatch_report_delivery, user["tenant_id"], report_id, body.recipient)
    return envelope(
        request,
        {
            **payload,
            "truth": _report_truth(
                report_count=1,
                delivery_status=payload.get("delivery_status"),
                artifacts=payload.get("artifact_readiness", {}).get("statuses", []),
            ),
        },
    )
