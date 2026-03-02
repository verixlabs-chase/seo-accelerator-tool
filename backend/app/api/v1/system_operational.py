from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.deps import require_platform_role
from app.api.response import envelope
from app.services import infra_service
from app.services.operational_telemetry_service import snapshot_operational_health


router = APIRouter(tags=["ops"])


@router.get("/system/operational-health")
def system_operational_health(
    request: Request,
    _user: dict = Depends(require_platform_role({"platform_owner", "platform_admin"})),
) -> dict:
    queue_status = infra_service.celery_queue_status()
    for queue_name in queue_status["active_queues"]:
        infra_service.queue_depth_count(str(queue_name))

    payload = snapshot_operational_health()
    payload["active_queues"] = list(queue_status["active_queues"])
    payload["worker_count_per_queue"] = dict(queue_status["worker_count_per_queue"])
    return envelope(request, {"operational_health": payload})
