import json
from hashlib import sha256
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.events import emit_event
from app.models.campaign import Campaign
from app.models.crawl import TechnicalIssue
from app.models.intelligence import IntelligenceScore
from app.models.local import ReviewVelocitySnapshot
from app.models.rank import RankingSnapshot
from app.models.reporting import MonthlyReport, ReportArtifact, ReportDeliveryEvent, ReportSchedule
from app.providers import get_email_adapter
from app.services import analytics_service
from app.services.strategy_engine.thresholds import version_id as strategy_threshold_version

REPORT_SCHEDULE_MAX_RETRIES = 3


def _campaign_or_404(db: Session, tenant_id: str, campaign_id: str, organization_id: str | None = None) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None or campaign.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    if organization_id is not None and campaign.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    return campaign


def _report_query(db: Session, tenant_id: str, organization_id: str | None = None):
    query = (
        db.query(MonthlyReport)
        .join(Campaign, Campaign.id == MonthlyReport.campaign_id)
        .filter(
            MonthlyReport.tenant_id == tenant_id,
            Campaign.tenant_id == tenant_id,
        )
    )
    if organization_id is not None:
        query = query.filter(Campaign.organization_id == organization_id)
    return query


def aggregate_kpis(db: Session, tenant_id: str, campaign_id: str, month_number: int, organization_id: str | None = None) -> dict:
    _campaign_or_404(db, tenant_id, campaign_id, organization_id)
    latest_metric = analytics_service.get_latest_campaign_daily_metric(
        db,
        campaign_id=campaign_id,
        on_or_before=datetime.now(UTC),
    )
    ranking_count = db.query(RankingSnapshot).filter(RankingSnapshot.tenant_id == tenant_id, RankingSnapshot.campaign_id == campaign_id).count()
    issues_count = db.query(TechnicalIssue).filter(TechnicalIssue.tenant_id == tenant_id, TechnicalIssue.campaign_id == campaign_id).count()
    latest_score = (
        db.query(IntelligenceScore)
        .filter(IntelligenceScore.tenant_id == tenant_id, IntelligenceScore.campaign_id == campaign_id)
        .order_by(IntelligenceScore.captured_at.desc())
        .first()
    )
    latest_velocity = (
        db.query(ReviewVelocitySnapshot)
        .filter(ReviewVelocitySnapshot.tenant_id == tenant_id, ReviewVelocitySnapshot.campaign_id == campaign_id)
        .order_by(ReviewVelocitySnapshot.captured_at.desc())
        .first()
    )
    return {
        "month_number": month_number,
        "rank_snapshots": ranking_count,
        "technical_issues": int(latest_metric.technical_issue_count) if latest_metric is not None else issues_count,
        "intelligence_score": (
            latest_metric.intelligence_score if latest_metric is not None else (latest_score.score_value if latest_score else None)
        ),
        "reviews_last_30d": int(latest_metric.reviews_last_30d) if latest_metric is not None else (latest_velocity.reviews_last_30d if latest_velocity else 0),
        "avg_rating_last_30d": (
            latest_metric.avg_rating_last_30d
            if latest_metric is not None and latest_metric.avg_rating_last_30d is not None
            else (latest_velocity.avg_rating_last_30d if latest_velocity else 0.0)
        ),
    }


def render_html(kpis: dict, campaign_name: str) -> str:
    return f"""
<html>
  <body>
    <h1>{campaign_name} - Month {kpis['month_number']} Report</h1>
    <ul>
      <li>Rank Snapshots: {kpis['rank_snapshots']}</li>
      <li>Technical Issues: {kpis['technical_issues']}</li>
      <li>Intelligence Score: {kpis['intelligence_score']}</li>
      <li>Reviews (30d): {kpis['reviews_last_30d']}</li>
      <li>Avg Rating (30d): {kpis['avg_rating_last_30d']}</li>
    </ul>
  </body>
</html>
""".strip()


def render_html_report(kpis: dict, report_id: str, campaign_name: str) -> str:
    out_dir = Path("generated_reports")
    out_dir.mkdir(exist_ok=True)
    path = out_dir / f"{report_id}.html"
    path.write_text(render_html(kpis, campaign_name), encoding="utf-8")
    return str(path)


def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _build_simple_pdf(lines: list[str]) -> bytes:
    content_lines = ["BT", "/F1 12 Tf", "50 780 Td", "14 TL"]
    for idx, line in enumerate(lines):
        escaped = _pdf_escape(line[:220])
        if idx == 0:
            content_lines.append(f"({_pdf_escape(line[:220])}) Tj")
        else:
            content_lines.append(f"T* ({escaped}) Tj")
    content_lines.append("ET")
    stream = "\n".join(content_lines).encode("latin-1", errors="replace")

    objects = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n",
        b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
        b"5 0 obj << /Length " + str(len(stream)).encode("ascii") + b" >> stream\n" + stream + b"\nendstream endobj\n",
    ]
    header = b"%PDF-1.4\n"
    xref_offsets = [0]
    body = b""
    offset = len(header)
    for obj in objects:
        xref_offsets.append(offset)
        body += obj
        offset += len(obj)
    xref_pos = len(header) + len(body)
    xref = [f"xref\n0 {len(xref_offsets)}\n".encode("ascii"), b"0000000000 65535 f \n"]
    for pos in xref_offsets[1:]:
        xref.append(f"{pos:010d} 00000 n \n".encode("ascii"))
    trailer = f"trailer << /Size {len(xref_offsets)} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode("ascii")
    return header + body + b"".join(xref) + trailer


def render_pdf_report(kpis: dict, report_id: str, campaign_name: str) -> str:
    out_dir = Path("generated_reports")
    out_dir.mkdir(exist_ok=True)
    path = out_dir / f"{report_id}.pdf"
    metadata = {
        "report_id": report_id,
        "strategy_profile_version": strategy_threshold_version,
        "version_hash": sha256(f"{strategy_threshold_version}:{json.dumps(kpis, sort_keys=True)}".encode("utf-8")).hexdigest(),
    }
    lines = [
        f"{campaign_name} - Month {kpis['month_number']} Report",
        f"Rank Snapshots: {kpis['rank_snapshots']}",
        f"Technical Issues: {kpis['technical_issues']}",
        f"Intelligence Score: {kpis['intelligence_score']}",
        f"Reviews (30d): {kpis['reviews_last_30d']}",
        f"Avg Rating (30d): {kpis['avg_rating_last_30d']}",
        f"Strategy Version: {metadata['strategy_profile_version']}",
        f"Version Hash: {metadata['version_hash']}",
    ]
    path.write_bytes(_build_simple_pdf(lines))
    return str(path)


def _artifact_readiness(artifact: ReportArtifact) -> dict:
    storage_path = (artifact.storage_path or "").strip()
    path = Path(storage_path)
    if path.is_file():
        return {
            "artifact_id": artifact.id,
            "artifact_type": artifact.artifact_type,
            "storage_mode": "local_disk",
            "ready": True,
            "durable": False,
            "reason": None,
        }

    return {
        "artifact_id": artifact.id,
        "artifact_type": artifact.artifact_type,
        "storage_mode": "local_disk" if storage_path else "unknown",
        "ready": False,
        "durable": False,
        "reason": "missing_file" if storage_path else "missing_storage_path",
    }


def artifact_contract(artifact: ReportArtifact) -> dict:
    readiness = _artifact_readiness(artifact)
    storage_path = (artifact.storage_path or "").strip()
    return {
        "id": artifact.id,
        "artifact_type": artifact.artifact_type,
        "storage_path": storage_path,
        "storage_mode": readiness["storage_mode"],
        "ready": readiness["ready"],
        "retrievable": False,
        "durable": readiness["durable"],
        "reason": readiness["reason"],
        "created_at": artifact.created_at,
    }


def _report_delivery_readiness(artifacts: list[ReportArtifact]) -> dict:
    statuses = [_artifact_readiness(artifact) for artifact in artifacts]
    return {
        "ready": any(item["ready"] for item in statuses),
        "statuses": statuses,
    }


def generate_report(db: Session, tenant_id: str, campaign_id: str, month_number: int, organization_id: str | None = None) -> MonthlyReport:
    campaign = _campaign_or_404(db, tenant_id, campaign_id, organization_id)
    kpis = aggregate_kpis(db, tenant_id, campaign_id, month_number, organization_id)
    report = MonthlyReport(
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        month_number=month_number,
        report_status="generated",
        summary_json=json.dumps(kpis),
    )
    db.add(report)
    db.flush()

    html_artifact = ReportArtifact(
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        report_id=report.id,
        artifact_type="html",
        storage_path=render_html_report(kpis, report.id, campaign.name),
    )
    pdf_path = render_pdf_report(kpis, report.id, campaign.name)
    pdf_artifact = ReportArtifact(
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        report_id=report.id,
        artifact_type="pdf",
        storage_path=pdf_path,
    )
    db.add(html_artifact)
    db.add(pdf_artifact)
    emit_event(
        db,
        tenant_id=tenant_id,
        event_type="report.generated",
        payload={"campaign_id": campaign_id, "report_id": report.id, "month_number": month_number},
    )
    db.commit()
    db.refresh(report)
    return report


def list_reports(db: Session, tenant_id: str, campaign_id: str | None = None, organization_id: str | None = None) -> list[MonthlyReport]:
    if campaign_id is not None:
        _campaign_or_404(db, tenant_id, campaign_id, organization_id)
    query = _report_query(db, tenant_id, organization_id)
    if campaign_id:
        query = query.filter(MonthlyReport.campaign_id == campaign_id)
    return query.order_by(MonthlyReport.generated_at.desc()).all()


def get_report_status_summary(db: Session, tenant_id: str, campaign_id: str) -> dict:
    _campaign_or_404(db, tenant_id, campaign_id)
    grouped = (
        db.query(MonthlyReport.report_status, func.count(MonthlyReport.id))
        .filter(MonthlyReport.tenant_id == tenant_id, MonthlyReport.campaign_id == campaign_id)
        .group_by(MonthlyReport.report_status)
        .all()
    )
    latest = (
        db.query(MonthlyReport)
        .filter(MonthlyReport.tenant_id == tenant_id, MonthlyReport.campaign_id == campaign_id)
        .order_by(MonthlyReport.generated_at.desc())
        .first()
    )
    schedule = (
        db.query(ReportSchedule)
        .filter(ReportSchedule.tenant_id == tenant_id, ReportSchedule.campaign_id == campaign_id)
        .first()
    )
    schedule_failure = bool(schedule and schedule.last_status in {"retry_pending", "max_retries_exceeded"})
    return {
        "total_reports": int(sum(int(row[1]) for row in grouped)),
        "counts_by_status": {str(row[0]): int(row[1]) for row in grouped},
        "latest_report_status": latest.report_status if latest else None,
        "latest_generated_at": latest.generated_at if latest else None,
        "schedule": {
            "enabled": schedule.enabled if schedule else None,
            "retry_count": schedule.retry_count if schedule else 0,
            "last_status": schedule.last_status if schedule else None,
            "next_run_at": schedule.next_run_at if schedule else None,
            "has_failure": schedule_failure,
        },
    }


def get_report(db: Session, tenant_id: str, report_id: str, organization_id: str | None = None) -> MonthlyReport:
    row = _report_query(db, tenant_id, organization_id).filter(MonthlyReport.id == report_id).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    return row


def get_report_artifacts(db: Session, tenant_id: str, report_id: str, organization_id: str | None = None) -> list[ReportArtifact]:
    report = get_report(db, tenant_id, report_id, organization_id)
    return (
        db.query(ReportArtifact)
        .filter(
            ReportArtifact.tenant_id == tenant_id,
            ReportArtifact.report_id == report_id,
            ReportArtifact.campaign_id == report.campaign_id,
        )
        .order_by(ReportArtifact.created_at.desc())
        .all()
    )


def get_report_deliveries(db: Session, tenant_id: str, report_id: str, organization_id: str | None = None) -> list[ReportDeliveryEvent]:
    report = get_report(db, tenant_id, report_id, organization_id)
    return (
        db.query(ReportDeliveryEvent)
        .filter(
            ReportDeliveryEvent.tenant_id == tenant_id,
            ReportDeliveryEvent.report_id == report_id,
            ReportDeliveryEvent.campaign_id == report.campaign_id,
        )
        .order_by(ReportDeliveryEvent.created_at.desc())
        .all()
    )


def deliver_report(db: Session, tenant_id: str, report_id: str, recipient: str, organization_id: str | None = None) -> dict:
    report = get_report(db, tenant_id, report_id, organization_id)
    artifacts = get_report_artifacts(db, tenant_id, report_id, organization_id)
    readiness = _report_delivery_readiness(artifacts)
    if not readiness["ready"]:
        event = ReportDeliveryEvent(
            tenant_id=tenant_id,
            campaign_id=report.campaign_id,
            report_id=report.id,
            delivery_channel="email",
            delivery_status="failed",
            recipient=recipient,
            sent_at=None,
        )
        db.add(event)
        db.commit()
        return {
            "report_id": report.id,
            "delivery_status": event.delivery_status,
            "recipient": recipient,
            "reason": "artifact_not_ready",
            "artifact_readiness": readiness,
        }

    adapter = get_email_adapter()
    delivery = adapter.send_email(
        recipient=recipient,
        subject=f"LSOS Report {report.id}",
        body=f"Report {report.id} delivery notification",
    )
    status_value = delivery.get("status", "failed")
    event = ReportDeliveryEvent(
        tenant_id=tenant_id,
        campaign_id=report.campaign_id,
        report_id=report.id,
        delivery_channel="email",
        delivery_status="sent" if status_value == "sent" else "failed",
        recipient=recipient,
        sent_at=datetime.now(UTC) if status_value == "sent" else None,
    )
    report.report_status = "delivered" if status_value == "sent" else "generated"
    db.add(event)
    db.commit()
    return {
        "report_id": report.id,
        "delivery_status": event.delivery_status,
        "recipient": recipient,
        "artifact_readiness": readiness,
    }


def _validate_timezone(timezone: str) -> str:
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid timezone") from exc
    return timezone


def get_report_schedule(db: Session, tenant_id: str, campaign_id: str, organization_id: str | None = None) -> ReportSchedule | None:
    _campaign_or_404(db, tenant_id, campaign_id, organization_id)
    return (
        db.query(ReportSchedule)
        .filter(ReportSchedule.tenant_id == tenant_id, ReportSchedule.campaign_id == campaign_id)
        .first()
    )


def upsert_report_schedule(
    db: Session,
    tenant_id: str,
    campaign_id: str,
    cadence: str,
    timezone: str,
    next_run_at: datetime,
    enabled: bool,
    organization_id: str | None = None,
) -> ReportSchedule:
    campaign = _campaign_or_404(db, tenant_id, campaign_id, organization_id)
    _validate_timezone(timezone)
    if cadence not in {"daily", "weekly", "monthly"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid cadence")
    normalized_next_run_at = next_run_at if next_run_at.tzinfo else next_run_at.replace(tzinfo=UTC)
    row = get_report_schedule(db, tenant_id, campaign_id, organization_id)
    if row is None:
        row = ReportSchedule(
            tenant_id=tenant_id,
            organization_id=campaign.organization_id,
            campaign_id=campaign_id,
            cadence=cadence,
            timezone=timezone,
            next_run_at=normalized_next_run_at,
            enabled=enabled,
            retry_count=0,
            last_status="scheduled",
        )
        db.add(row)
    else:
        row.cadence = cadence
        row.timezone = timezone
        row.next_run_at = normalized_next_run_at
        row.enabled = enabled
        row.last_status = "scheduled" if enabled else "disabled"
    db.commit()
    db.refresh(row)
    return row


def _advance_next_run(next_run_at: datetime, cadence: str) -> datetime:
    if cadence == "daily":
        return next_run_at + timedelta(days=1)
    if cadence == "weekly":
        return next_run_at + timedelta(days=7)
    return next_run_at + timedelta(days=30)


def mark_schedule_attempt_failure(db: Session, tenant_id: str, campaign_id: str, error_message: str) -> dict:
    row = get_report_schedule(db, tenant_id, campaign_id)
    if row is None:
        return {"campaign_id": campaign_id, "status": "missing_schedule", "should_retry": False, "retry_count": 0}
    if not row.enabled or row.last_status == "max_retries_exceeded":
        return {
            "campaign_id": campaign_id,
            "status": row.last_status,
            "retry_count": row.retry_count,
            "max_retries": REPORT_SCHEDULE_MAX_RETRIES,
            "should_retry": False,
            "error": error_message,
        }
    row.retry_count += 1
    if row.retry_count >= REPORT_SCHEDULE_MAX_RETRIES:
        row.enabled = False
        row.last_status = "max_retries_exceeded"
        should_retry = False
    else:
        row.last_status = "retry_pending"
        should_retry = True
    db.commit()
    return {
        "campaign_id": campaign_id,
        "status": row.last_status,
        "retry_count": row.retry_count,
        "max_retries": REPORT_SCHEDULE_MAX_RETRIES,
        "should_retry": should_retry,
        "error": error_message,
    }


def run_due_report_schedule(db: Session, tenant_id: str, campaign_id: str) -> dict:
    row = get_report_schedule(db, tenant_id, campaign_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report schedule not found")
    if not row.enabled:
        return {"campaign_id": campaign_id, "status": "disabled", "scheduled": False}
    now = datetime.now(UTC)
    next_run = row.next_run_at if row.next_run_at.tzinfo else row.next_run_at.replace(tzinfo=UTC)
    if next_run > now:
        return {"campaign_id": campaign_id, "status": "not_due", "scheduled": False, "next_run_at": next_run}
    campaign = _campaign_or_404(db, tenant_id, campaign_id)
    report = generate_report(db, tenant_id, campaign_id, campaign.month_number)
    row.retry_count = 0
    row.last_status = "success"
    row.next_run_at = _advance_next_run(next_run, row.cadence)
    db.commit()
    return {
        "campaign_id": campaign_id,
        "scheduled": True,
        "status": "success",
        "report_id": report.id,
        "next_run_at": row.next_run_at,
    }
