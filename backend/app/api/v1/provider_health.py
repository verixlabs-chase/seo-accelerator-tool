from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.api.deps import require_roles
from app.api.response import envelope
from app.db.session import get_db
from app.intelligence.executors.plugin_telemetry import WORDPRESS_CAPABILITY, WORDPRESS_PROVIDER_NAME
from app.models.campaign import Campaign
from app.models.provider_health import ProviderHealthState
from app.models.provider_policy import ProviderPolicy
from app.services.provider_credentials_service import get_organization_provider_credentials, get_platform_provider_credentials
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


@router.get("/wordpress-execution-setup")
def wordpress_execution_setup(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None or campaign.tenant_id != user["tenant_id"]:
        raise HTTPException(status_code=404, detail="Campaign not found")

    settings = get_settings()
    environment = settings.app_env.lower()
    site_id = campaign.domain
    health_row = (
        db.query(ProviderHealthState)
        .filter(
            ProviderHealthState.tenant_id == user["tenant_id"],
            ProviderHealthState.environment == environment,
            ProviderHealthState.provider_name == WORDPRESS_PROVIDER_NAME,
            ProviderHealthState.capability == f"{WORDPRESS_CAPABILITY}:{site_id}",
        )
        .order_by(ProviderHealthState.updated_at.desc())
        .first()
    )

    if environment == "test":
        return envelope(
            request,
            {
                "campaign_id": campaign.id,
                "provider_name": WORDPRESS_PROVIDER_NAME,
                "mode": "test",
                "configured": True,
                "execution_ready": True,
                "blocked": False,
                "health_state": "healthy",
                "credential_source": "test_environment",
                "credential_mode": "test_environment",
                "missing_fields": [],
                "missing_requirements": [],
                "plugin_version": "test",
                "breaker_state": "closed",
                "last_error_code": None,
                "last_error_at": None,
                "last_success_at": None,
                "status_summary": "Test mode is active. Live WordPress credentials are not required in this environment.",
                "disabled_reason": None,
            },
        )

    organization_id = campaign.organization_id
    policy = None
    if organization_id:
        policy = (
            db.query(ProviderPolicy)
            .filter(
                ProviderPolicy.organization_id == organization_id,
                ProviderPolicy.provider_name == WORDPRESS_PROVIDER_NAME,
            )
            .first()
        )
    credential_mode = policy.credential_mode if policy is not None else "platform"
    organization_credentials = (
        get_organization_provider_credentials(db, organization_id, WORDPRESS_PROVIDER_NAME)
        if organization_id
        else {}
    )
    platform_credentials = get_platform_provider_credentials(db, WORDPRESS_PROVIDER_NAME)

    selected_credentials: dict = {}
    credential_source = "none"
    if credential_mode == "platform":
        selected_credentials = platform_credentials
        credential_source = "platform" if platform_credentials else "none"
    elif credential_mode == "byo_optional":
        if organization_credentials:
            selected_credentials = organization_credentials
            credential_source = "organization"
        elif platform_credentials:
            selected_credentials = platform_credentials
            credential_source = "platform"
        else:
            selected_credentials = {}
    elif credential_mode == "byo_required":
        selected_credentials = organization_credentials
        credential_source = "organization" if organization_credentials else "none"

    base_url = str(selected_credentials.get("base_url") or selected_credentials.get("site_url") or "").strip()
    plugin_token = str(selected_credentials.get("plugin_token") or selected_credentials.get("bearer_token") or "").strip()
    shared_secret = str(selected_credentials.get("shared_secret") or "").strip()

    missing_fields: list[str] = []
    missing_requirements: list[str] = []
    if not organization_id:
        missing_fields.append("organization")
        missing_requirements.append("Connect this campaign to an organization before live WordPress execution can run.")
    if credential_source == "none":
        missing_requirements.append("WordPress plugin credentials have not been configured for this organization yet.")
    if not base_url:
        missing_fields.append("base_url")
        missing_requirements.append("Add the WordPress base URL so the platform knows where to send mutations.")
    if not plugin_token:
        missing_fields.append("plugin_token")
        missing_requirements.append("Add the WordPress plugin token so live mutation requests can authenticate.")
    if not shared_secret:
        missing_fields.append("shared_secret")
        missing_requirements.append("Add the WordPress shared secret so mutation requests can be signed safely.")

    configured = len(missing_fields) == 0
    breaker_state = str(health_row.breaker_state).lower() if health_row is not None else "unknown"
    blocked = breaker_state == "open"
    execution_ready = configured and not blocked
    if blocked:
        status_summary = "WordPress plugin health is currently blocked for this site. Resolve the plugin issue before running live mutations."
    elif configured and health_row is not None:
        status_summary = "WordPress execution is configured and the latest plugin health signal is healthy."
    elif configured:
        status_summary = "WordPress execution is configured, but the plugin has not reported health yet."
    else:
        status_summary = missing_requirements[0] if missing_requirements else "WordPress execution is not configured yet."

    disabled_reason = None if execution_ready else status_summary

    return envelope(
        request,
        {
            "campaign_id": campaign.id,
            "provider_name": WORDPRESS_PROVIDER_NAME,
            "mode": "live",
            "configured": configured,
            "execution_ready": execution_ready,
            "blocked": blocked,
            "health_state": "blocked" if blocked else ("healthy" if health_row is not None else "unknown"),
            "credential_source": credential_source,
            "credential_mode": credential_mode,
            "missing_fields": missing_fields,
            "missing_requirements": missing_requirements,
            "plugin_version": health_row.provider_version if health_row is not None else None,
            "breaker_state": breaker_state,
            "last_error_code": health_row.last_error_code if health_row is not None else None,
            "last_error_at": health_row.last_error_at.isoformat() if health_row and health_row.last_error_at else None,
            "last_success_at": health_row.last_success_at.isoformat() if health_row and health_row.last_success_at else None,
            "status_summary": status_summary,
            "disabled_reason": disabled_reason,
        },
    )
