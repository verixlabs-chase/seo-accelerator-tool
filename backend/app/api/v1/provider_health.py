from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.api.deps import require_roles
from app.api.response import envelope
from app.db.session import get_db, set_session_security_context
from app.intelligence.executors import wordpress_plugin
from app.intelligence.executors.plugin_telemetry import (
    WORDPRESS_CAPABILITY,
    WORDPRESS_PROVIDER_NAME,
    verify_plugin_version,
)
from app.models.campaign import Campaign
from app.models.provider_health import ProviderHealthState
from app.models.provider_policy import ProviderPolicy
from app.services.audit_service import write_audit_log
from app.services.commercial_plan_service import (
    FEATURE_WORDPRESS_EXECUTION,
    require_commercial_feature,
)
from app.services.cost_economics_service import CostEconomicsError
from app.services.provider_credentials_service import get_organization_provider_credentials, get_platform_provider_credentials
from app.services.provider_telemetry_service import ProviderTelemetryService
from app.services.wordpress_connection_service import (
    WordPressConnectionError,
    disconnect_site,
    exchange_pairing,
    get_site_connection,
    get_site_credentials,
    pairing_is_active,
    start_pairing,
)
from app.services.wordpress_content_inventory_service import (
    WordPressContentInventoryError,
    get_wordpress_content_inventory,
    latest_sync_summary,
    sync_wordpress_content,
)
from app.services.wordpress_plugin_package_service import (
    WordPressPluginPackageError,
    build_wordpress_plugin_package,
    get_wordpress_plugin_package_metadata,
)


router = APIRouter(prefix="/provider-health", tags=["provider-health"])


class WordPressPairingExchangeIn(BaseModel):
    pairing_code: str = Field(..., min_length=20, max_length=40)
    site_url: str = Field(..., min_length=8, max_length=2048)
    plugin_version: str = Field(default="", max_length=40)


def _campaign_or_404(db: Session, tenant_id: str, organization_id: str | None, campaign_id: str) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None or campaign.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if organization_id is not None and campaign.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


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
    campaign = _campaign_or_404(db, user["tenant_id"], user.get("organization_id"), campaign_id)
    try:
        require_commercial_feature(
            db,
            organization_id=campaign.organization_id,
            feature_code=FEATURE_WORDPRESS_EXECUTION,
        )
    except CostEconomicsError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"message": str(exc), "reason_code": exc.reason_code},
        ) from exc

    settings = get_settings()
    environment = settings.app_env.lower()
    plugin_package = get_wordpress_plugin_package_metadata()
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
        content_sync = latest_sync_summary(db, campaign_id=campaign.id)
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
                "plugin_package": plugin_package,
                "breaker_state": "closed",
                "last_error_code": None,
                "last_error_at": None,
                "last_success_at": None,
                "status_summary": "Test mode is active. Live WordPress credentials are not required in this environment.",
                "disabled_reason": None,
                **content_sync,
            },
        )

    organization_id = campaign.organization_id
    site_connection = get_site_connection(db, campaign_id=campaign.id)
    site_credentials = get_site_credentials(db, campaign_id=campaign.id)
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
    if site_credentials:
        selected_credentials = site_credentials
        credential_source = "site"
        credential_mode = "site_pairing"
    elif site_connection is not None and site_connection.status == "disconnected":
        selected_credentials = {}
        credential_source = "disconnected"
        credential_mode = "site_pairing"
    elif credential_mode == "platform":
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
        missing_requirements.append("Finish setting up this business before connecting WordPress.")
    if not base_url:
        missing_fields.append("base_url")
    if not plugin_token:
        missing_fields.append("plugin_token")
    if not shared_secret:
        missing_fields.append("shared_secret")
    if credential_source == "disconnected":
        missing_requirements.append(
            "This website was disconnected. Create a new pairing code when you are ready to reconnect it."
        )
    elif not selected_credentials:
        missing_requirements.append(
            "Create a pairing code, then enter it under Settings → InsightOS in WordPress."
        )
    elif not base_url or not plugin_token or not shared_secret:
        missing_requirements.append(
            "This older connection is incomplete. Replace it with a new pairing code."
        )

    configured = len(missing_fields) == 0
    breaker_state = str(health_row.breaker_state).lower() if health_row is not None else "unknown"
    supported_version = bool(
        health_row is not None
        and health_row.provider_version
        and verify_plugin_version({"plugin_version": health_row.provider_version})
    )
    handshake_confirmed = bool(
        health_row is not None
        and health_row.last_success_at is not None
        and breaker_state == "closed"
        and supported_version
    )
    blocked = breaker_state == "open" or (health_row is not None and not supported_version)
    execution_ready = configured and handshake_confirmed and not blocked
    if health_row is not None and not supported_version:
        status_summary = "Update the InsightOS WordPress plugin, then test the connection again."
    elif blocked:
        status_summary = "WordPress needs attention before a website update can run."
    elif configured and handshake_confirmed:
        status_summary = "WordPress is connected and ready for approved website updates."
    elif configured:
        status_summary = "The connection is saved. Test it before running a website update."
    else:
        status_summary = missing_requirements[0] if missing_requirements else "WordPress is not connected yet."

    disabled_reason = None if execution_ready else status_summary

    content_sync = latest_sync_summary(db, campaign_id=campaign.id)
    return envelope(
        request,
        {
            "campaign_id": campaign.id,
            "provider_name": WORDPRESS_PROVIDER_NAME,
            "mode": "live",
            "configured": configured,
            "execution_ready": execution_ready,
            "blocked": blocked,
            "health_state": "blocked" if blocked else ("healthy" if handshake_confirmed else "unknown"),
            "credential_source": credential_source,
            "credential_mode": credential_mode,
            "pairing_pending": pairing_is_active(site_connection),
            "pairing_expires_at": (
                site_connection.pairing_expires_at.isoformat()
                if pairing_is_active(site_connection) and site_connection is not None
                else None
            ),
            "missing_fields": missing_fields,
            "missing_requirements": missing_requirements,
            "plugin_version": health_row.provider_version if health_row is not None else None,
            "plugin_package": plugin_package,
            "breaker_state": breaker_state,
            "last_error_code": health_row.last_error_code if health_row is not None else None,
            "last_error_at": health_row.last_error_at.isoformat() if health_row and health_row.last_error_at else None,
            "last_success_at": health_row.last_success_at.isoformat() if health_row and health_row.last_success_at else None,
            "status_summary": status_summary,
            "disabled_reason": disabled_reason,
            **content_sync,
        },
    )


@router.get("/wordpress-plugin-download")
def download_wordpress_plugin(
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> Response:
    campaign = _campaign_or_404(db, user["tenant_id"], user.get("organization_id"), campaign_id)
    try:
        require_commercial_feature(
            db,
            organization_id=campaign.organization_id,
            feature_code=FEATURE_WORDPRESS_EXECUTION,
        )
        package = build_wordpress_plugin_package()
    except CostEconomicsError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"message": str(exc), "reason_code": exc.reason_code},
        ) from exc
    except WordPressPluginPackageError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "message": "The WordPress plugin download is temporarily unavailable.",
                "reason_code": "wordpress_plugin_package_unavailable",
            },
        ) from exc

    write_audit_log(
        db,
        tenant_id=campaign.tenant_id,
        actor_user_id=user["id"],
        event_type="wordpress.plugin.package_downloaded",
        payload={
            "campaign_id": campaign.id,
            "filename": package.filename,
            "version": package.version,
            "sha256": package.sha256,
        },
    )
    db.commit()
    return Response(
        content=package.content,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{package.filename}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "X-InsightOS-Plugin-Version": package.version,
            "X-InsightOS-Package-SHA256": package.sha256,
        },
    )


@router.post("/wordpress-pairing/start")
def start_wordpress_pairing(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    campaign = _campaign_or_404(db, user["tenant_id"], user.get("organization_id"), campaign_id)
    try:
        require_commercial_feature(
            db,
            organization_id=campaign.organization_id,
            feature_code=FEATURE_WORDPRESS_EXECUTION,
        )
        result = start_pairing(db, campaign=campaign)
    except CostEconomicsError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"message": str(exc), "reason_code": exc.reason_code},
        ) from exc
    except WordPressConnectionError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"message": str(exc), "reason_code": exc.reason_code},
        ) from exc
    write_audit_log(
        db,
        tenant_id=campaign.tenant_id,
        actor_user_id=user["id"],
        event_type="wordpress.site.pairing_started",
        payload={"campaign_id": campaign.id, "site_url": result["site_url"]},
    )
    db.commit()
    return envelope(
        request,
        {
            **result,
            "instructions": [
                "Install and activate the InsightOS plugin in WordPress.",
                "Open InsightOS in the WordPress Settings menu.",
                "Enter this one-time code and choose Connect website.",
            ],
        },
    )


@router.post("/wordpress-pairing/exchange")
def exchange_wordpress_pairing(
    request: Request,
    body: WordPressPairingExchangeIn,
    db: Session = Depends(get_db),
) -> dict:
    """Public plugin exchange secured by a short-lived high-entropy one-time code."""

    # The plugin does not have a user session yet: exchanging the one-time code
    # is what creates its site credentials.  Use a narrowly scoped internal RLS
    # context for this transaction so the service can find the hashed code and
    # write the matching tenant audit event.  This endpoint performs no general
    # tenant reads and returns data only after the site-scoped code is verified.
    set_session_security_context(
        db,
        tenant_id=None,
        organization_id=None,
        user_id="wordpress-pairing-exchange",
        platform_access=True,
    )
    try:
        result = exchange_pairing(
            db,
            pairing_code=body.pairing_code,
            site_url=body.site_url,
            plugin_version=body.plugin_version,
        )
    except WordPressConnectionError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"message": str(exc), "reason_code": exc.reason_code},
        ) from exc
    campaign = db.get(Campaign, result["campaign_id"])
    if campaign is not None:
        write_audit_log(
            db,
            tenant_id=campaign.tenant_id,
            actor_user_id=None,
            event_type="wordpress.site.paired",
            payload={"campaign_id": campaign.id, "site_url": result["site_url"]},
        )
        db.commit()
    return envelope(request, result)


@router.delete("/wordpress-connection")
def disconnect_wordpress_connection(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    campaign = _campaign_or_404(db, user["tenant_id"], user.get("organization_id"), campaign_id)
    connection = get_site_connection(db, campaign_id=campaign.id)
    if connection is None or connection.status != "connected":
        raise HTTPException(
            status_code=409,
            detail={
                "message": "This website does not have a site-specific WordPress connection.",
                "reason_code": "wordpress_site_connection_missing",
            },
        )
    try:
        wordpress_plugin.disconnect_connection(db, campaign_id=campaign.id)
    except wordpress_plugin.WordPressExecutionError as exc:
        raise HTTPException(
            status_code=502,
            detail={"message": str(exc), "reason_code": exc.reason_code},
        ) from exc
    disconnect_site(db, campaign_id=campaign.id)
    write_audit_log(
        db,
        tenant_id=campaign.tenant_id,
        actor_user_id=user["id"],
        event_type="wordpress.site.disconnected",
        payload={"campaign_id": campaign.id, "site_url": connection.site_url},
    )
    db.query(ProviderHealthState).filter(
        ProviderHealthState.tenant_id == campaign.tenant_id,
        ProviderHealthState.provider_name == WORDPRESS_PROVIDER_NAME,
        ProviderHealthState.capability == f"{WORDPRESS_CAPABILITY}:{campaign.domain}",
    ).delete(synchronize_session=False)
    db.commit()
    return envelope(
        request,
        {
            "campaign_id": campaign.id,
            "disconnected": True,
            "message": "WordPress is disconnected and its connection keys were removed.",
        },
    )


@router.post("/wordpress-execution-check")
def check_wordpress_execution_connection(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    campaign = _campaign_or_404(db, user["tenant_id"], user.get("organization_id"), campaign_id)
    try:
        require_commercial_feature(
            db,
            organization_id=campaign.organization_id,
            feature_code=FEATURE_WORDPRESS_EXECUTION,
        )
        result = wordpress_plugin.check_connection(db, campaign_id=campaign.id)
    except CostEconomicsError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"message": str(exc), "reason_code": exc.reason_code},
        ) from exc
    except wordpress_plugin.WordPressExecutionError as exc:
        raise HTTPException(
            status_code=502,
            detail={"message": str(exc), "reason_code": exc.reason_code},
        ) from exc
    return envelope(
        request,
        {
            **result,
            "campaign_id": campaign.id,
            "message": "Connection confirmed. WordPress changes still require review and approval.",
        },
    )


@router.get("/wordpress-content-inventory")
def wordpress_content_inventory(
    request: Request,
    campaign_id: str = Query(...),
    limit: int = Query(default=100, ge=1, le=500),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    campaign = _campaign_or_404(db, user["tenant_id"], user.get("organization_id"), campaign_id)
    try:
        require_commercial_feature(
            db,
            organization_id=campaign.organization_id,
            feature_code=FEATURE_WORDPRESS_EXECUTION,
        )
    except CostEconomicsError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"message": str(exc), "reason_code": exc.reason_code},
        ) from exc
    return envelope(
        request,
        get_wordpress_content_inventory(db, campaign=campaign, limit=limit),
    )


@router.post("/wordpress-content-sync")
def refresh_wordpress_content_inventory(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    campaign = _campaign_or_404(db, user["tenant_id"], user.get("organization_id"), campaign_id)
    try:
        require_commercial_feature(
            db,
            organization_id=campaign.organization_id,
            feature_code=FEATURE_WORDPRESS_EXECUTION,
        )
        result = sync_wordpress_content(db, campaign=campaign)
    except CostEconomicsError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"message": str(exc), "reason_code": exc.reason_code},
        ) from exc
    except WordPressContentInventoryError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"message": str(exc), "reason_code": exc.reason_code},
        ) from exc
    except wordpress_plugin.WordPressExecutionError as exc:
        raise HTTPException(
            status_code=502,
            detail={"message": str(exc), "reason_code": exc.reason_code},
        ) from exc
    write_audit_log(
        db,
        tenant_id=campaign.tenant_id,
        actor_user_id=user["id"],
        event_type="wordpress.content_inventory.synced",
        payload={
            "campaign_id": campaign.id,
            "pages_found": result["summary"]["pages_found"],
            "sync_run_id": result.get("sync_run_id"),
        },
    )
    db.commit()
    return envelope(
        request,
        {
            **result,
            "message": "Website content is up to date. Nothing on the website was changed.",
        },
    )
