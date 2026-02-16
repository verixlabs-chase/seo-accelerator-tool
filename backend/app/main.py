from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import inspect

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging, request_context_middleware
from app.db.session import engine, SessionLocal
from app.services.auth_service import seed_local_admin

settings = get_settings()
configure_logging()

@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    if not inspect(engine).has_table("users"):
        yield
    else:
        db = SessionLocal()
        try:
            seed_local_admin(db)
        finally:
            db.close()
        yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.middleware("http")(request_context_middleware)
app.include_router(api_router, prefix=settings.api_v1_prefix)
