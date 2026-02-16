import json
from datetime import UTC, datetime
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.campaign import Campaign
from app.models.crawl import TechnicalIssue
from app.models.intelligence import IntelligenceScore
from app.models.local import ReviewVelocitySnapshot
from app.models.rank import RankingSnapshot
from app.models.reporting import MonthlyReport, ReportArtifact, ReportDeliveryEvent


def _campaign_or_404(db: Session, tenant_id: str, campaign_id: str) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None or campaign.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    return campaign


def aggregate_kpis(db: Session, tenant_id: str, campaign_id: str, month_number: int) -> dict:
    _campaign_or_404(db, tenant_id, campaign_id)
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
        "technical_issues": issues_count,
        "intelligence_score": latest_score.score_value if latest_score else None,
        "reviews_last_30d": latest_velocity.reviews_last_30d if latest_velocity else 0,
        "avg_rating_last_30d": latest_velocity.avg_rating_last_30d if latest_velocity else 0.0,
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


def render_pdf_placeholder(html: str, report_id: str) -> str:
    out_dir = Path("generated_reports")
    out_dir.mkdir(exist_ok=True)
    path = out_dir / f"{report_id}.pdf.txt"
    path.write_text(f"PDF_PLACEHOLDER\n\n{html}", encoding="utf-8")
    return str(path)


def generate_report(db: Session, tenant_id: str, campaign_id: str, month_number: int) -> MonthlyReport:
    campaign = _campaign_or_404(db, tenant_id, campaign_id)
    kpis = aggregate_kpis(db, tenant_id, campaign_id, month_number)
    report = MonthlyReport(
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        month_number=month_number,
        report_status="generated",
        summary_json=json.dumps(kpis),
    )
    db.add(report)
    db.flush()

    html = render_html(kpis, campaign.name)
    html_artifact = ReportArtifact(
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        report_id=report.id,
        artifact_type="html",
        storage_path=f"inline://{report.id}.html",
    )
    pdf_path = render_pdf_placeholder(html, report.id)
    pdf_artifact = ReportArtifact(
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        report_id=report.id,
        artifact_type="pdf",
        storage_path=pdf_path,
    )
    db.add(html_artifact)
    db.add(pdf_artifact)
    db.commit()
    db.refresh(report)
    return report


def list_reports(db: Session, tenant_id: str, campaign_id: str | None = None) -> list[MonthlyReport]:
    query = db.query(MonthlyReport).filter(MonthlyReport.tenant_id == tenant_id)
    if campaign_id:
        query = query.filter(MonthlyReport.campaign_id == campaign_id)
    return query.order_by(MonthlyReport.generated_at.desc()).all()


def get_report(db: Session, tenant_id: str, report_id: str) -> MonthlyReport:
    row = db.get(MonthlyReport, report_id)
    if row is None or row.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    return row


def get_report_artifacts(db: Session, tenant_id: str, report_id: str) -> list[ReportArtifact]:
    return (
        db.query(ReportArtifact)
        .filter(ReportArtifact.tenant_id == tenant_id, ReportArtifact.report_id == report_id)
        .order_by(ReportArtifact.created_at.desc())
        .all()
    )


def deliver_report(db: Session, tenant_id: str, report_id: str, recipient: str) -> dict:
    report = get_report(db, tenant_id, report_id)
    event = ReportDeliveryEvent(
        tenant_id=tenant_id,
        campaign_id=report.campaign_id,
        report_id=report.id,
        delivery_channel="email",
        delivery_status="sent",
        recipient=recipient,
        sent_at=datetime.now(UTC),
    )
    report.report_status = "delivered"
    db.add(event)
    db.commit()
    return {"report_id": report.id, "delivery_status": "sent", "recipient": recipient}

