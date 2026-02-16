from fastapi import APIRouter

from app.api.v1 import auth, campaigns, competitors, content, crawl, health, local, rank

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(campaigns.router)
api_router.include_router(crawl.router)
api_router.include_router(rank.router)
api_router.include_router(competitors.router)
api_router.include_router(content.content_router)
api_router.include_router(content.internal_links_router)
api_router.include_router(local.local_router)
api_router.include_router(local.reviews_router)
