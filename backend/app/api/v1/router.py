from fastapi import APIRouter

from app.api.v1 import (
    auth,
    authority,
    campaigns,
    competitors,
    content,
    crawl,
    dashboard,
    entity,
    health,
    intelligence,
    local,
    rank,
    recommendations,
    reference_library,
    reports,
    tenants,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(tenants.router)
api_router.include_router(auth.router)
api_router.include_router(campaigns.router)
api_router.include_router(crawl.router)
api_router.include_router(entity.router)
api_router.include_router(rank.router)
api_router.include_router(competitors.router)
api_router.include_router(content.content_router)
api_router.include_router(content.internal_links_router)
api_router.include_router(local.local_router)
api_router.include_router(local.reviews_router)
api_router.include_router(authority.authority_router)
api_router.include_router(authority.citations_router)
api_router.include_router(intelligence.intelligence_router)
api_router.include_router(intelligence.campaign_intelligence_router)
api_router.include_router(recommendations.router)
api_router.include_router(dashboard.router)
api_router.include_router(reference_library.router)
api_router.include_router(reports.router)
