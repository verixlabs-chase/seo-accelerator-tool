from fastapi import APIRouter

from app.api.v1 import auth, campaigns, competitors, crawl, health, rank

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(campaigns.router)
api_router.include_router(crawl.router)
api_router.include_router(rank.router)
api_router.include_router(competitors.router)
