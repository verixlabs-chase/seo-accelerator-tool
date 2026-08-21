from __future__ import annotations

import hmac
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api.response import envelope
from app.core.config import get_settings
from app.db.session import get_db
from app.services import durable_job_service
from app.services.rate_limit_store import PostgresFixedWindowRateLimitStore

router = APIRouter(prefix="/internal/jobs", tags=["internal-jobs"], include_in_schema=False)
logger = logging.getLogger("lsos.api.internal_jobs")


def _require_cron_secret(request: Request) -> None:
    expected = get_settings().cron_secret.strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Durable job cron is not configured.",
        )
    supplied = request.headers.get("Authorization", "")
    if not hmac.compare_digest(supplied, f"Bearer {expected}"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid cron authorization.")


def _prune_rate_limit_counters(*, invocation_id: str) -> dict[str, int | str | bool]:
    runtime_settings = get_settings()
    result: dict[str, int | str | bool] = {
        "attempted": False,
        "deleted": 0,
        "batches": 0,
        "status": "not_required",
    }
    if not (
        bool(getattr(runtime_settings, "rate_limit_enabled", False))
        and getattr(runtime_settings, "rate_limit_backend", "redis") == "postgres"
    ):
        return result

    result["attempted"] = True
    # Cleanup is maintenance work, not request admission. Smaller batches keep
    # index churn predictable on entry-level hosted PostgreSQL while a separate
    # bounded timeout gives each batch enough time to complete.
    batch_size = 1_000
    # The Vercel function has a 60-second ceiling. Run at most one maintenance
    # batch, then reserve the remaining budget for durable customer work.
    max_batches = 1
    try:
        store = PostgresFixedWindowRateLimitStore(
            statement_timeout_ms=2_000,
            lock_timeout_ms=500,
        )
        for _ in range(max_batches):
            deleted = store.prune_expired(
                retention_seconds=172_800,
                batch_size=batch_size,
            )
            result["deleted"] = int(result["deleted"]) + deleted
            result["batches"] = int(result["batches"]) + 1
            if deleted < batch_size:
                break
        result["status"] = (
            "batch_limit_reached"
            if int(result["batches"]) == max_batches and deleted == batch_size
            else "completed"
        )
    except Exception as exc:  # noqa: BLE001 - cleanup must not block durable jobs
        result["status"] = "unavailable"
        logger.warning(
            "rate_limit_cleanup_unavailable",
            extra={
                "event": "rate_limit_cleanup_unavailable",
                "exception_type": exc.__class__.__name__,
                "invocation_id": invocation_id or None,
            },
        )
    return result


@router.get("/drain")
def drain_durable_jobs(
    request: Request,
    batch_size: int | None = Query(default=None, ge=1, le=25),
    db: Session = Depends(get_db),
) -> dict:
    _require_cron_secret(request)
    invocation_id = request.headers.get("x-vercel-id", "").strip()[:96]
    worker_id = invocation_id or f"cron-{uuid.uuid4()}"
    cleanup_result = _prune_rate_limit_counters(invocation_id=invocation_id)
    result = durable_job_service.drain_platform_jobs(
        db,
        worker_id=worker_id,
        batch_size=batch_size,
        time_budget_seconds=40,
    )
    result["rate_limit_cleanup"] = cleanup_result
    return envelope(request, result)
