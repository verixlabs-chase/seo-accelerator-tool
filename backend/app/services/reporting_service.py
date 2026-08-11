import json
import logging
import re
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
from app.models.organization import Organization
from app.models.rank import RankingSnapshot
from app.models.reporting import MonthlyReport, ReportArtifact, ReportDeliveryEvent, ReportSchedule
from app.providers import get_email_adapter
from app.services import analytics_service
from app.services import premium_report_service
from app.services import report_artifact_storage_service
from app.services import report_pdf_service

REPORT_SCHEDULE_MAX_RETRIES = 3
logger = logging.getLogger("lsos.reporting")

PORTFOLIO_REPORT_METRIC_KEYS = (
    "google_visits",
    "google_appearances",
    "average_google_position",
    "tracked_keyword_position",
    "tracked_keywords_top_10",
    "website_issues",
    "reviews_last_30d",
    "average_rating",
    "visibility_health",
)


def _report_failure_metadata(exc: Exception, *, stage: str) -> dict[str, str | None]:
    original = getattr(exc, "orig", None)
    diagnostic = getattr(original, "diag", None)
    database_message = str(original or exc)
    database_object_match = re.search(
        r'(?:table|relation)\s+"?([A-Za-z_][A-Za-z0-9_]*)"?',
        database_message,
        flags=re.IGNORECASE,
    )
    normalized_message = database_message.lower()
    if "row-level security" in normalized_message:
        failure_category = "row_level_security"
    elif "permission denied" in normalized_message or "insufficient privilege" in normalized_message:
        failure_category = "table_privilege"
    else:
        failure_category = None
    return {
        "event": "report_generation_failed",
        "stage": stage,
        "error_type": type(exc).__name__,
        "error_module": type(exc).__module__,
        "database_error_type": type(original).__name__ if original is not None else None,
        "database_sqlstate": getattr(original, "sqlstate", None),
        "database_constraint": getattr(diagnostic, "constraint_name", None),
        "database_column": getattr(diagnostic, "column_name", None),
        "database_table": getattr(diagnostic, "table_name", None),
        "database_object": database_object_match.group(1) if database_object_match else None,
        "failure_category": failure_category,
    }


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
    snapshot = premium_report_service.normalize_snapshot(kpis, campaign_name)
    return premium_report_service.render_report_html(snapshot)


def render_html_report(kpis: dict, report_id: str, campaign_name: str) -> str:
    out_dir = report_artifact_storage_service.local_report_artifact_root()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{report_id}.html"
    path.write_text(render_html(kpis, campaign_name), encoding="utf-8")
    return str(path)


def render_pdf_report(kpis: dict, report_id: str, campaign_name: str) -> str:
    out_dir = report_artifact_storage_service.local_report_artifact_root()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{report_id}.pdf"
    snapshot = premium_report_service.normalize_snapshot(kpis, campaign_name)
    path.write_bytes(report_pdf_service.build_report_pdf(snapshot))
    return str(path)


def _artifact_readiness(artifact: ReportArtifact) -> dict:
    storage_path = (artifact.storage_path or "").strip()
    storage_key = (artifact.storage_key or "").strip()
    storage_mode = str(artifact.storage_mode or "local_disk")
    ready = bool(artifact.ready)
    if ready and storage_mode == "local_disk":
        ready = Path(storage_path or storage_key).is_file()
    elif ready and storage_mode == "database_private":
        ready = artifact.content_blob is not None
    elif ready and storage_mode == "s3_private":
        try:
            storage = report_artifact_storage_service.get_report_artifact_storage()
            ready = storage.storage_mode == "s3_private" and storage.exists(storage_key, storage_path)
        except Exception:
            ready = False

    if ready:
        return {
            "artifact_id": artifact.id,
            "artifact_type": artifact.artifact_type,
            "storage_mode": storage_mode,
            "ready": True,
            "durable": bool(artifact.durable),
            "reason": None,
        }

    return {
        "artifact_id": artifact.id,
        "artifact_type": artifact.artifact_type,
        "storage_mode": storage_mode if (storage_path or storage_key) else "unknown",
        "ready": False,
        "durable": bool(artifact.durable),
        "reason": "artifact_unavailable" if (storage_path or storage_key) else "missing_storage_path",
    }


def artifact_contract(artifact: ReportArtifact) -> dict:
    readiness = _artifact_readiness(artifact)
    storage_path = (artifact.storage_path or "").strip()
    return {
        "id": artifact.id,
        "artifact_type": artifact.artifact_type,
        "storage_path": storage_path if readiness["storage_mode"] == "local_disk" else "",
        "storage_mode": readiness["storage_mode"],
        "ready": readiness["ready"],
        "retrievable": readiness["ready"],
        "durable": readiness["durable"],
        "content_type": artifact.content_type,
        "byte_size": artifact.byte_size,
        "checksum_sha256": artifact.checksum_sha256,
        "reason": readiness["reason"],
        "created_at": artifact.created_at,
    }


def _store_snapshot_artifacts(
    *,
    tenant_id: str,
    report_id: str,
    snapshot: dict,
) -> dict[str, report_artifact_storage_service.StoredReportArtifact]:
    storage = report_artifact_storage_service.get_report_artifact_storage()
    html_content = premium_report_service.render_report_html(snapshot).encode("utf-8")
    pdf_content = report_pdf_service.build_report_pdf(snapshot)
    return {
        "html": storage.put_bytes(
            tenant_id=tenant_id,
            report_id=report_id,
            filename="report.html",
            content_type="text/html; charset=utf-8",
            content=html_content,
        ),
        "pdf": storage.put_bytes(
            tenant_id=tenant_id,
            report_id=report_id,
            filename="report.pdf",
            content_type="application/pdf",
            content=pdf_content,
        ),
    }


def _apply_stored_artifact(artifact: ReportArtifact, stored: report_artifact_storage_service.StoredReportArtifact) -> None:
    artifact.storage_path = stored.storage_path
    artifact.storage_mode = stored.storage_mode
    artifact.storage_key = stored.storage_key
    artifact.content_type = stored.content_type
    artifact.byte_size = stored.byte_size
    artifact.checksum_sha256 = stored.checksum_sha256
    artifact.content_blob = stored.content
    artifact.durable = stored.durable
    artifact.ready = stored.ready


def _report_delivery_readiness(artifacts: list[ReportArtifact]) -> dict:
    statuses = [_artifact_readiness(artifact) for artifact in artifacts]
    return {
        "ready": any(item["ready"] for item in statuses),
        "statuses": statuses,
    }


def generate_report(db: Session, tenant_id: str, campaign_id: str, month_number: int, organization_id: str | None = None) -> MonthlyReport:
    campaign = _campaign_or_404(db, tenant_id, campaign_id, organization_id)
    stage = "build_snapshot"
    try:
        snapshot = premium_report_service.build_report_snapshot(
            db,
            tenant_id=tenant_id,
            campaign=campaign,
            month_number=month_number,
        )
        stage = "create_report_record"
        report = MonthlyReport(
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            month_number=month_number,
            report_status="generated",
            summary_json=json.dumps(snapshot, sort_keys=True),
        )
        db.add(report)
        db.flush()
        storage = report_artifact_storage_service.get_report_artifact_storage()
        stage = f"store_artifacts_{storage.storage_mode}"
        stored_artifacts = _store_snapshot_artifacts(
            tenant_id=tenant_id,
            report_id=report.id,
            snapshot=snapshot,
        )
        stage = "create_artifact_records"
        for artifact_type, stored in stored_artifacts.items():
            artifact = ReportArtifact(
                tenant_id=tenant_id,
                campaign_id=campaign_id,
                report_id=report.id,
                artifact_type=artifact_type,
                storage_path=stored.storage_path,
            )
            _apply_stored_artifact(artifact, stored)
            db.add(artifact)
        db.flush()
        stage = "emit_report_event"
        emit_event(
            db,
            tenant_id=tenant_id,
            event_type="report.generated",
            payload={
                "campaign_id": campaign_id,
                "report_id": report.id,
                "month_number": month_number,
                "snapshot_hash": snapshot["snapshot_hash"],
                "snapshot_version": snapshot["schema_version"],
            },
        )
        db.flush()
        stage = "commit_report"
        db.commit()
        db.refresh(report)
        return report
    except Exception as exc:
        db.rollback()
        logger.error(
            "report_generation_failed",
            extra={
                **_report_failure_metadata(exc, stage=stage),
                "campaign_id": campaign_id,
                "month_number": month_number,
            },
        )
        raise


def get_report_readiness(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
    organization_id: str | None = None,
) -> dict:
    campaign = _campaign_or_404(db, tenant_id, campaign_id, organization_id)
    return premium_report_service.build_report_readiness(
        db,
        tenant_id=tenant_id,
        campaign=campaign,
    )


def get_report_snapshot(
    db: Session,
    tenant_id: str,
    report_id: str,
    organization_id: str | None = None,
) -> dict:
    report = get_report(db, tenant_id, report_id, organization_id)
    campaign = _campaign_or_404(db, tenant_id, report.campaign_id, organization_id)
    try:
        payload = json.loads(report.summary_json or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The saved report snapshot cannot be read",
        ) from exc
    return premium_report_service.normalize_snapshot(payload, campaign.name)


def get_portfolio_report_comparison(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
) -> dict:
    campaigns = (
        db.query(Campaign)
        .filter(
            Campaign.tenant_id == tenant_id,
            Campaign.organization_id == organization_id,
        )
        .order_by(Campaign.name.asc(), Campaign.id.asc())
        .all()
    )
    campaign_ids = [campaign.id for campaign in campaigns]
    reports = (
        _report_query(db, tenant_id, organization_id)
        .filter(MonthlyReport.campaign_id.in_(campaign_ids))
        .order_by(MonthlyReport.generated_at.desc(), MonthlyReport.id.desc())
        .all()
        if campaign_ids
        else []
    )
    latest_by_campaign: dict[str, MonthlyReport] = {}
    for report in reports:
        latest_by_campaign.setdefault(report.campaign_id, report)

    locations: list[dict] = []
    period_keys: set[tuple[str, str, str, str]] = set()
    comparable_count = 0
    legacy_count = 0
    invalid_count = 0

    for campaign in campaigns:
        report = latest_by_campaign.get(campaign.id)
        if report is None:
            locations.append(
                {
                    "campaign_id": campaign.id,
                    "business_location_id": campaign.business_location_id,
                    "location_name": campaign.name,
                    "domain": campaign.domain,
                    "comparison_state": "missing_report",
                    "comparison_message": "Create a report for this location before comparing it.",
                    "report": None,
                    "period": None,
                    "metrics": [],
                    "wins_count": 0,
                    "risks_count": 0,
                    "next_action": None,
                    "source_freshness": "unknown",
                }
            )
            continue

        try:
            raw_snapshot = json.loads(report.summary_json or "{}")
        except json.JSONDecodeError:
            raw_snapshot = {}
        snapshot = premium_report_service.normalize_snapshot(raw_snapshot, campaign.name)
        schema_version = str(snapshot.get("schema_version") or "")
        is_rpt1_snapshot = schema_version in {"rpt1-owner-v1", premium_report_service.REPORT_SNAPSHOT_VERSION}
        snapshot_valid = is_rpt1_snapshot and premium_report_service.validate_snapshot(snapshot)
        if not is_rpt1_snapshot:
            comparison_state = "legacy_report"
            comparison_message = "Create a new report to include this location in a trustworthy comparison."
            legacy_count += 1
        elif not snapshot_valid:
            comparison_state = "invalid_snapshot"
            comparison_message = "This saved report did not pass its integrity check and is excluded."
            invalid_count += 1
        else:
            comparison_state = "ready"
            comparison_message = "This location can be compared using its saved report facts."
            comparable_count += 1

        period = snapshot.get("period") if isinstance(snapshot.get("period"), dict) else {}
        if comparison_state == "ready":
            period_keys.add(
                (
                    str(period.get("start") or ""),
                    str(period.get("end") or ""),
                    str(period.get("comparison_start") or ""),
                    str(period.get("comparison_end") or ""),
                )
            )

        metric_items = snapshot.get("metrics") if isinstance(snapshot.get("metrics"), list) else []
        metric_lookup = {
            str(metric.get("key")): metric
            for metric in metric_items
            if isinstance(metric, dict) and metric.get("key")
        }
        metrics = [
            metric_lookup[key]
            for key in PORTFOLIO_REPORT_METRIC_KEYS
            if key in metric_lookup
        ] if comparison_state == "ready" else []
        risks = snapshot.get("risks") if isinstance(snapshot.get("risks"), list) else []
        wins = snapshot.get("wins") if isinstance(snapshot.get("wins"), list) else []
        priorities = snapshot.get("next_priorities") if isinstance(snapshot.get("next_priorities"), list) else []
        first_priority = priorities[0] if priorities and isinstance(priorities[0], dict) else None
        snapshot_campaign = snapshot.get("campaign") if isinstance(snapshot.get("campaign"), dict) else {}
        source = snapshot.get("source") if isinstance(snapshot.get("source"), dict) else {}
        locations.append(
            {
                "campaign_id": campaign.id,
                "business_location_id": campaign.business_location_id,
                "location_name": snapshot_campaign.get("location_name") or campaign.name,
                "domain": snapshot_campaign.get("domain") or campaign.domain,
                "comparison_state": comparison_state,
                "comparison_message": comparison_message,
                "report": {
                    "id": report.id,
                    "month_number": report.month_number,
                    "status": report.report_status,
                    "generated_at": report.generated_at.isoformat(),
                    "snapshot_hash": snapshot.get("snapshot_hash") or None,
                    "snapshot_version": schema_version,
                },
                "period": period or None,
                "metrics": metrics,
                "wins_count": len(wins) if comparison_state == "ready" else 0,
                "risks_count": len(risks) if comparison_state == "ready" else 0,
                "next_action": (
                    {
                        "title": first_priority.get("title"),
                        "why_it_matters": first_priority.get("why_it_matters"),
                    }
                    if first_priority and comparison_state == "ready"
                    else None
                ),
                "source_freshness": source.get("freshness_state") or "unknown",
            }
        )

    periods_aligned = comparable_count >= 2 and len(period_keys) == 1
    warnings: list[str] = []
    missing_count = len(campaigns) - comparable_count - legacy_count - invalid_count
    if missing_count:
        warnings.append(
            f"{missing_count} location{'s' if missing_count != 1 else ''} "
            f"{'need' if missing_count != 1 else 'needs'} a report before "
            f"{'they' if missing_count != 1 else 'it'} can be compared."
        )
    if legacy_count:
        warnings.append(
            f"{legacy_count} location{'s have' if legacy_count != 1 else ' has'} an older report format and "
            f"{'need' if legacy_count != 1 else 'needs'} a new report."
        )
    if invalid_count:
        warnings.append(
            f"{invalid_count} location{'s are' if invalid_count != 1 else ' is'} excluded because the saved report did not pass its integrity check."
        )
    if comparable_count >= 2 and not periods_aligned:
        warnings.append(
            "The saved report dates do not match, so the locations are shown separately without naming a leader."
        )

    ready_locations = [item for item in locations if item["comparison_state"] == "ready"]
    ready_locations.sort(
        key=lambda item: (
            -int(item["risks_count"]),
            str(item["location_name"]).lower(),
        )
    )
    focus_location = ready_locations[0] if ready_locations else None
    if periods_aligned and focus_location and focus_location["risks_count"]:
        focus = {
            "campaign_id": focus_location["campaign_id"],
            "location_name": focus_location["location_name"],
            "reason": (
                f"Start here because its saved report has {focus_location['risks_count']} "
                f"item{'s' if focus_location['risks_count'] != 1 else ''} needing attention."
            ),
        }
    else:
        focus = None

    return {
        "organization_id": organization_id,
        "checked_at": datetime.now(UTC).isoformat(),
        "source_contract": "latest_frozen_report_snapshot_per_location",
        "totals_are_combined": False,
        "location_count": len(campaigns),
        "comparable_location_count": comparable_count,
        "periods_aligned": periods_aligned,
        "comparison_ready": periods_aligned,
        "common_period": (
            {
                "start": next(iter(period_keys))[0],
                "end": next(iter(period_keys))[1],
                "comparison_start": next(iter(period_keys))[2],
                "comparison_end": next(iter(period_keys))[3],
            }
            if periods_aligned
            else None
        ),
        "warnings": warnings,
        "focus": focus,
        "locations": locations,
    }


def build_portfolio_report_snapshot(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
) -> dict:
    """Assemble a reproducible portfolio document from frozen location reports."""
    comparison = get_portfolio_report_comparison(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
    )
    if not comparison["comparison_ready"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Create matching reports for at least two locations before downloading "
                "an all-location report."
            ),
        )

    organization = (
        db.query(Organization)
        .filter(Organization.id == organization_id)
        .one_or_none()
    )
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    locations: list[dict] = []
    assembled_at = ""
    for item in comparison["locations"]:
        if item["comparison_state"] != "ready" or not item.get("report"):
            continue
        report_id = str(item["report"]["id"])
        snapshot = get_report_snapshot(
            db,
            tenant_id=tenant_id,
            report_id=report_id,
            organization_id=organization_id,
        )
        if not premium_report_service.validate_snapshot(snapshot):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A saved location report did not pass its integrity check.",
            )
        assembled_at = max(assembled_at, str(item["report"].get("generated_at") or ""))
        locations.append(
            {
                "campaign_id": item["campaign_id"],
                "business_location_id": item.get("business_location_id"),
                "location_name": item["location_name"],
                "domain": item.get("domain"),
                "report": item["report"],
                "period": snapshot.get("period") or {},
                "metrics": snapshot.get("metrics") or [],
                "wins": snapshot.get("wins") or [],
                "risks": snapshot.get("risks") or [],
                "next_priorities": snapshot.get("next_priorities") or [],
                "source": snapshot.get("source") or {},
            }
        )

    payload = {
        "schema_version": "rpt1-portfolio-v1",
        "source_contract": "exact_frozen_report_snapshots_per_location",
        "totals_are_combined": False,
        "assembled_at": assembled_at,
        "organization": {
            "id": organization.id,
            "name": organization.name,
        },
        "brand": {
            "product_name": "InsightOS",
            "publisher": "VerixLabs",
            "prepared_for": organization.name,
        },
        "period": comparison["common_period"],
        "focus": comparison["focus"],
        "location_count": len(locations),
        "organization_location_count": comparison["location_count"],
        "warnings": comparison["warnings"],
        "excluded_locations": [
            {
                "campaign_id": item["campaign_id"],
                "location_name": item["location_name"],
                "domain": item.get("domain"),
                "state": item["comparison_state"],
                "reason": item["comparison_message"],
            }
            for item in comparison["locations"]
            if item["comparison_state"] != "ready"
        ],
        "locations": locations,
    }
    packed = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    payload["snapshot_hash"] = sha256(packed.encode("utf-8")).hexdigest()
    return payload


def regenerate_report_artifacts(
    db: Session,
    tenant_id: str,
    report_id: str,
    organization_id: str | None = None,
) -> dict:
    report = get_report(db, tenant_id, report_id, organization_id)
    _campaign_or_404(db, tenant_id, report.campaign_id, organization_id)
    snapshot = get_report_snapshot(db, tenant_id, report_id, organization_id)
    if snapshot.get("schema_version") == premium_report_service.REPORT_SNAPSHOT_VERSION and not premium_report_service.validate_snapshot(snapshot):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The saved report snapshot failed its integrity check",
        )

    stored_artifacts = _store_snapshot_artifacts(
        tenant_id=tenant_id,
        report_id=report.id,
        snapshot=snapshot,
    )
    artifacts = get_report_artifacts(db, tenant_id, report_id, organization_id)
    by_type = {artifact.artifact_type: artifact for artifact in artifacts}
    for artifact_type, stored in stored_artifacts.items():
        artifact = by_type.get(artifact_type)
        if artifact is None:
            artifact = ReportArtifact(
                tenant_id=tenant_id,
                campaign_id=report.campaign_id,
                report_id=report.id,
                artifact_type=artifact_type,
                storage_path=stored.storage_path,
            )
            db.add(artifact)
        _apply_stored_artifact(artifact, stored)
    report.report_status = "generated"
    emit_event(
        db,
        tenant_id=tenant_id,
        event_type="report.regenerated",
        payload={
            "campaign_id": report.campaign_id,
            "report_id": report.id,
            "snapshot_hash": snapshot.get("snapshot_hash"),
            "snapshot_version": snapshot.get("schema_version"),
        },
    )
    db.commit()
    return {
        "report_id": report.id,
        "snapshot_hash": snapshot.get("snapshot_hash"),
        "snapshot_version": snapshot.get("schema_version"),
        "snapshot_valid": premium_report_service.validate_snapshot(snapshot),
        "artifacts": [artifact_contract(item) for item in get_report_artifacts(db, tenant_id, report_id, organization_id)],
    }


def read_report_artifact(
    db: Session,
    tenant_id: str,
    report_id: str,
    artifact_id: str,
    organization_id: str | None = None,
) -> tuple[ReportArtifact, bytes]:
    artifacts = get_report_artifacts(db, tenant_id, report_id, organization_id)
    artifact = next((item for item in artifacts if item.id == artifact_id), None)
    if artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report file not found")
    readiness = _artifact_readiness(artifact)
    if not readiness["ready"]:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Report file is not available")
    if artifact.storage_mode == "database_private":
        content = bytes(artifact.content_blob or b"")
    elif artifact.storage_mode == "local_disk":
        storage = report_artifact_storage_service.LocalReportArtifactStorage()
        try:
            content = storage.read_bytes(artifact.storage_key or "", artifact.storage_path or "")
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Report file is not available") from exc
    else:
        storage = report_artifact_storage_service.get_report_artifact_storage()
        try:
            content = storage.read_bytes(artifact.storage_key or "", artifact.storage_path or "")
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Report file is not available") from exc
    if artifact.checksum_sha256 and sha256(content).hexdigest() != artifact.checksum_sha256:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Report file failed its integrity check")
    return artifact, content


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
    attempt_number = (
        db.query(func.count(ReportDeliveryEvent.id))
        .filter(
            ReportDeliveryEvent.tenant_id == tenant_id,
            ReportDeliveryEvent.report_id == report.id,
            ReportDeliveryEvent.recipient == recipient,
        )
        .scalar()
        or 0
    ) + 1
    if not readiness["ready"]:
        failed_at = datetime.now(UTC)
        event = ReportDeliveryEvent(
            tenant_id=tenant_id,
            campaign_id=report.campaign_id,
            report_id=report.id,
            delivery_channel="email",
            delivery_status="failed",
            recipient=recipient,
            attempt_number=attempt_number,
            failure_reason="artifact_not_ready",
            sent_at=None,
            failed_at=failed_at,
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
    delivery_status = "sent" if status_value == "sent" else "retry_pending" if status_value == "deferred" else "failed"
    event_time = datetime.now(UTC)
    event = ReportDeliveryEvent(
        tenant_id=tenant_id,
        campaign_id=report.campaign_id,
        report_id=report.id,
        delivery_channel="email",
        delivery_status=delivery_status,
        recipient=recipient,
        provider_message_id=delivery.get("message_id") or delivery.get("id"),
        attempt_number=attempt_number,
        failure_reason=delivery.get("reason") if delivery_status != "sent" else None,
        sent_at=event_time if delivery_status == "sent" else None,
        failed_at=event_time if delivery_status == "failed" else None,
    )
    report.report_status = "delivered" if delivery_status == "sent" else "generated"
    db.add(event)
    db.commit()
    return {
        "report_id": report.id,
        "delivery_status": event.delivery_status,
        "recipient": recipient,
        "attempt_number": event.attempt_number,
        "reason": event.failure_reason,
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


def mark_schedule_attempt_failure(
    db: Session,
    tenant_id: str,
    campaign_id: str,
    error_message: str,
    *,
    commit: bool = True,
) -> dict:
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
    if commit:
        db.commit()
    else:
        db.flush()
    return {
        "campaign_id": campaign_id,
        "status": row.last_status,
        "retry_count": row.retry_count,
        "max_retries": REPORT_SCHEDULE_MAX_RETRIES,
        "should_retry": should_retry,
        "error": error_message,
    }


def run_due_report_schedule(
    db: Session,
    tenant_id: str,
    campaign_id: str,
    *,
    commit: bool = True,
) -> dict:
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
    if commit:
        db.commit()
    else:
        db.flush()
    return {
        "campaign_id": campaign_id,
        "scheduled": True,
        "status": "success",
        "report_id": report.id,
        "next_run_at": row.next_run_at,
    }
