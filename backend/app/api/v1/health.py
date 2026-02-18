from fastapi import APIRouter, Request

from app.services import infra_service, observability_service

from app.api.response import envelope

router = APIRouter(tags=["ops"])


@router.get("/health")
def health(request: Request) -> dict:
    return envelope(request, {"status": "ok"})


@router.get("/health/readiness")
def readiness(request: Request) -> dict:
    db_ok = infra_service.db_connected()
    redis_ok = infra_service.redis_connected()
    if redis_ok:
        worker_ok = infra_service.worker_active()
        scheduler_ok = infra_service.scheduler_active()
    else:
        worker_ok = False
        scheduler_ok = False
    overall_ok = db_ok and redis_ok and worker_ok and scheduler_ok
    return envelope(
        request,
        {
            "status": "ready" if overall_ok else "degraded",
            "dependencies": {
                "database": db_ok,
                "redis": redis_ok,
                "worker_heartbeat": worker_ok,
                "scheduler_heartbeat": scheduler_ok,
            },
        },
    )


@router.get("/health/metrics")
def health_metrics(request: Request) -> dict:
    return envelope(request, observability_service.snapshot())


@router.get("/infra/status")
def infra_status(request: Request) -> dict:
    redis_ok = infra_service.redis_connected()
    worker_ok = infra_service.worker_active() if redis_ok else False
    scheduler_ok = infra_service.scheduler_active() if redis_ok else False
    return envelope(
        request,
        {
            "redis": "connected" if redis_ok else "not connected",
            "worker": "active" if worker_ok else "inactive",
            "scheduler": "active" if scheduler_ok else "inactive",
            "db": "connected" if infra_service.db_connected() else "not connected",
            "proxy": "configured" if infra_service.proxy_configured() else "not configured",
            "smtp": "configured" if infra_service.smtp_configured() else "not configured",
        },
    )
