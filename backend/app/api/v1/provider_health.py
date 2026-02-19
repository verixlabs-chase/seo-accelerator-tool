from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.response import envelope
from app.db.session import get_db
from app.services.provider_telemetry_service import ProviderTelemetryService


router = APIRouter(prefix="/provider-health", tags=["provider-health"])


@router.get("/summary")
def provider_health_summary(
    request: Request,
    environment: str = Query(default="production"),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    telemetry = ProviderTelemetryService(db)
    providers = telemetry.summary(tenant_id=user["tenant_id"], environment=environment)
    return envelope(
        request,
        {
            "tenant_id": user["tenant_id"],
            "environment": environment,
            "generated_at": datetime.now(UTC).isoformat(),
            "providers": providers,
        },
    )
