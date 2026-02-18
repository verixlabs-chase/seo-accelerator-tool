from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.alert_thresholds import ALERT_THRESHOLDS
from app.services import crawl_service, entity_service, intelligence_service, observability_service, reporting_service


def _derive_platform_state(snapshot: dict, report_summary: dict) -> tuple[str, dict]:
    slos = snapshot.get("slos", {})
    metrics = snapshot.get("metrics", {})
    worker_target = float(slos.get("worker_success_rate_target", 0.98))
    queue_target_ms = float(slos.get("queue_latency_seconds_target", 60.0)) * 1000.0
    crawl_target = float(slos.get("crawl_success_rate_target", 0.95))

    worker = float(metrics.get("worker_success_rate", 1.0))
    queue_ms = float(metrics.get("queue_latency_ms", 0.0))
    crawl_success = 1.0 - float(metrics.get("crawl_failure_rate", 0.0))
    queue_backlog = int(metrics.get("queue_backlog_tasks", 0))
    deadband = max(0.0, float(ALERT_THRESHOLDS.get("state_flip_flop_deadband_percent", 5)) / 100.0)
    worker_floor = worker_target - deadband
    queue_ceiling = queue_target_ms * (1.0 + deadband)
    crawl_floor = crawl_target - deadband

    checks = {
        "worker_success_rate": worker >= worker_floor,
        "queue_latency_ms": queue_ms <= queue_ceiling,
        "crawl_success_rate": crawl_success >= crawl_floor,
        "queue_backlog": queue_backlog <= 25,
        "report_schedule": not bool(report_summary.get("schedule", {}).get("has_failure")),
    }
    breaches = [key for key, passed in checks.items() if not passed]

    is_critical = (
        len(breaches) >= 2
        or worker < max(0.0, worker_target - 0.1)
        or queue_ms > (queue_target_ms * 2.0)
        or crawl_success < max(0.0, crawl_target - 0.1)
    )
    if not breaches:
        state = "Healthy"
    elif is_critical:
        state = "Critical"
    else:
        state = "Degraded"
    return state, {"checks": checks, "failed_checks": breaches}


def _technical_score_from_issue_count(issue_count: int) -> float:
    return round(max(0.0, min(100.0, 100.0 - (float(issue_count) * 4.0))), 2)


def build_dashboard(db: Session, tenant_id: str, campaign_id: str) -> dict:
    issues = crawl_service.list_issues(db, tenant_id=tenant_id, campaign_id=campaign_id)
    technical_score = _technical_score_from_issue_count(len(issues))

    entity_report = entity_service.get_latest_entity_report(db, tenant_id=tenant_id, campaign_id=campaign_id)
    recommendation_summary = intelligence_service.get_recommendation_summary(db, tenant_id=tenant_id, campaign_id=campaign_id)
    crawl_runs = crawl_service.list_runs(db, tenant_id=tenant_id, campaign_id=campaign_id)
    latest_run = crawl_runs[0] if crawl_runs else None
    report_summary = reporting_service.get_report_status_summary(db, tenant_id=tenant_id, campaign_id=campaign_id)

    slo_snapshot = observability_service.snapshot()
    platform_state, health_detail = _derive_platform_state(slo_snapshot, report_summary)
    dashboard_generated_at = datetime.now(UTC).isoformat()
    return {
        "campaign_id": campaign_id,
        "technical_score": technical_score,
        "entity_score": float(entity_report.get("entity_score", 0.0)),
        "recommendation_summary": recommendation_summary,
        "latest_crawl_status": {
            "crawl_run_id": latest_run.id if latest_run else None,
            "status": latest_run.status if latest_run else None,
            "created_at": latest_run.created_at.isoformat() if latest_run else None,
            "finished_at": latest_run.finished_at.isoformat() if latest_run and latest_run.finished_at else None,
        },
        "report_status_summary": {
            "total_reports": report_summary["total_reports"],
            "counts_by_status": report_summary["counts_by_status"],
            "latest_report_status": report_summary["latest_report_status"],
            "latest_generated_at": (
                report_summary["latest_generated_at"].isoformat() if report_summary["latest_generated_at"] else None
            ),
            "schedule": {
                "enabled": report_summary["schedule"]["enabled"],
                "retry_count": report_summary["schedule"]["retry_count"],
                "last_status": report_summary["schedule"]["last_status"],
                "next_run_at": (
                    report_summary["schedule"]["next_run_at"].isoformat()
                    if report_summary["schedule"]["next_run_at"]
                    else None
                ),
                "has_failure": report_summary["schedule"]["has_failure"],
            },
        },
        "slo_health_snapshot": {
            "slos": slo_snapshot.get("slos", {}),
            "metrics": slo_snapshot.get("metrics", {}),
            "alerts": slo_snapshot.get("alerts", {}),
            "evaluation": health_detail,
        },
        "platform_state": platform_state,
        "generated_at": dashboard_generated_at,
    }
