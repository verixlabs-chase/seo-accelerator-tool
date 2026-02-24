from fastapi import APIRouter

from app.api.v1 import (
    auth,
    authority,
    campaigns,
    competitors,
    content,
    crawl,
    debug_live_validation,
    dashboard,
    entity,
    google_oauth,
    health,
    intelligence,
    local,
    platform_control,
    provider_credentials,
    provider_health,
    provider_metrics,
    rank,
    recommendations,
    reference_library,
    reports,
    subaccounts,
    tenants,
)


def build_tenant_api_router(app_env: str) -> APIRouter:
    tenant_api_router = APIRouter()
    tenant_api_router.include_router(health.router)
    tenant_api_router.include_router(tenants.router)
    tenant_api_router.include_router(auth.router)
    tenant_api_router.include_router(campaigns.router)
    tenant_api_router.include_router(crawl.router)
    if app_env.lower() != 'production':
        tenant_api_router.include_router(debug_live_validation.router)
    tenant_api_router.include_router(entity.router)
    tenant_api_router.include_router(google_oauth.tenant_router)
    tenant_api_router.include_router(rank.router)
    tenant_api_router.include_router(competitors.router)
    tenant_api_router.include_router(content.content_router)
    tenant_api_router.include_router(content.internal_links_router)
    tenant_api_router.include_router(local.local_router)
    tenant_api_router.include_router(local.reviews_router)
    tenant_api_router.include_router(provider_credentials.tenant_router)
    tenant_api_router.include_router(provider_health.router)
    tenant_api_router.include_router(provider_metrics.router)
    tenant_api_router.include_router(authority.authority_router)
    tenant_api_router.include_router(authority.citations_router)
    tenant_api_router.include_router(intelligence.intelligence_router)
    tenant_api_router.include_router(intelligence.campaign_intelligence_router)
    tenant_api_router.include_router(recommendations.router)
    tenant_api_router.include_router(dashboard.router)
    tenant_api_router.include_router(reference_library.router)
    tenant_api_router.include_router(reports.router)
    tenant_api_router.include_router(subaccounts.router)
    return tenant_api_router


def build_control_plane_api_router() -> APIRouter:
    control_plane_api_router = APIRouter()
    control_plane_api_router.include_router(provider_credentials.control_plane_router)
    control_plane_api_router.include_router(platform_control.router)
    return control_plane_api_router
