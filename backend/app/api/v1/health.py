from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.services import infra_service, observability_service

from app.api.response import envelope

router = APIRouter(tags=["ops"])
settings = get_settings()


@router.get("/health")
def health(request: Request) -> dict:
    return envelope(
        request,
        {
            "status": "ok",
            "rate_limit": {
                "enabled": settings.rate_limit_enabled,
                "backend": settings.rate_limit_backend,
            },
        },
    )


@router.get("/health/readiness")
def readiness(request: Request) -> JSONResponse:
    db_ok = infra_service.db_connected()
    rate_limit_ok = (
        infra_service.rate_limit_store_connected()
        if settings.rate_limit_enabled
        else False
    )
    async_runtime_required = not settings.hosted_serverless
    if async_runtime_required:
        redis_ok: bool | None = infra_service.redis_connected()
        worker_ok: bool | None = infra_service.worker_active() if redis_ok else False
        scheduler_ok: bool | None = infra_service.scheduler_active() if redis_ok else False
    else:
        redis_ok = None
        worker_ok = None
        scheduler_ok = None
    async_runtime_ok = (
        bool(redis_ok and worker_ok and scheduler_ok)
        if async_runtime_required
        else True
    )
    overall_ok = bool(
        db_ok
        and settings.rate_limit_enabled
        and rate_limit_ok
        and async_runtime_ok
    )
    payload = envelope(
        request,
        {
            "status": "ready" if overall_ok else "degraded",
            "dependencies": {
                "database": db_ok,
                "rate_limit_enabled": settings.rate_limit_enabled,
                "rate_limit_backend": settings.rate_limit_backend,
                "rate_limit_store": rate_limit_ok,
                "async_runtime_required": async_runtime_required,
                "redis": redis_ok,
                "worker_heartbeat": worker_ok,
                "scheduler_heartbeat": scheduler_ok,
            },
        },
    )
    return JSONResponse(
        status_code=(
            status.HTTP_200_OK
            if overall_ok
            else status.HTTP_503_SERVICE_UNAVAILABLE
        ),
        content=payload,
        headers={"Cache-Control": "private, no-store"},
    )


@router.get("/health/metrics")
def health_metrics(request: Request) -> dict:
    return envelope(request, observability_service.snapshot())


@router.get("/infra/status")
def infra_status(request: Request) -> dict:
    async_runtime_required = not settings.hosted_serverless
    redis_ok = infra_service.redis_connected() if async_runtime_required else False
    worker_ok = (
        infra_service.worker_active() if async_runtime_required and redis_ok else False
    )
    scheduler_ok = (
        infra_service.scheduler_active() if async_runtime_required and redis_ok else False
    )
    rate_limit_ok = (
        infra_service.rate_limit_store_connected()
        if settings.rate_limit_enabled
        else False
    )
    return envelope(
        request,
        {
            "rate_limit_backend": settings.rate_limit_backend,
            "rate_limit_store": (
                "connected"
                if rate_limit_ok
                else "disabled"
                if not settings.rate_limit_enabled
                else "not connected"
            ),
            "redis": "connected" if redis_ok else "not connected",
            "worker": "active" if worker_ok else "inactive",
            "scheduler": "active" if scheduler_ok else "inactive",
            "db": "connected" if infra_service.db_connected() else "not connected",
            "proxy": "configured" if infra_service.proxy_configured() else "not configured",
            "smtp": "configured" if infra_service.smtp_configured() else "not configured",
        },
    )
