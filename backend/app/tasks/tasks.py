import json
from datetime import UTC, datetime

from app.tasks.celery_app import celery_app


@celery_app.task(name="ops.healthcheck.snapshot")
def ops_healthcheck_snapshot() -> dict:
    return {"timestamp": datetime.now(UTC).isoformat(), "status": "ok"}


@celery_app.task(name="campaigns.bootstrap_month_plan")
def campaigns_bootstrap_month_plan(campaign_id: str, tenant_id: str) -> dict:
    return {"campaign_id": campaign_id, "tenant_id": tenant_id, "month_number": 1, "status": "bootstrapped"}


@celery_app.task(name="audit.write_event")
def audit_write_event(event_type: str, tenant_id: str, actor_user_id: str | None = None, payload: dict | None = None) -> str:
    return json.dumps(
        {
            "event_type": event_type,
            "tenant_id": tenant_id,
            "actor_user_id": actor_user_id,
            "payload": payload or {},
        }
    )

