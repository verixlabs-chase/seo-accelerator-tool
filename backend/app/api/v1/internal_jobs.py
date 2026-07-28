from __future__ import annotations

import hmac
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api.response import envelope
from app.core.config import get_settings
from app.db.session import get_db
from app.services import durable_job_service

router = APIRouter(prefix="/internal/jobs", tags=["internal-jobs"], include_in_schema=False)


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


@router.get("/drain")
def drain_durable_jobs(
    request: Request,
    batch_size: int | None = Query(default=None, ge=1, le=25),
    db: Session = Depends(get_db),
) -> dict:
    _require_cron_secret(request)
    invocation_id = request.headers.get("x-vercel-id", "").strip()[:96]
    worker_id = invocation_id or f"cron-{uuid.uuid4()}"
    result = durable_job_service.drain_platform_jobs(
        db,
        worker_id=worker_id,
        batch_size=batch_size,
    )
    return envelope(request, result)
