from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import inspect

from app.api.response import exception_envelope
from app.api.v1.router import control_plane_api_router, tenant_api_router
from app.core.config import get_settings
from app.core.logging import configure_logging, request_context_middleware
from app.db.redis_client import get_redis_client
import app.db.session as db_session
from app.services.auth_service import seed_local_admin

settings = get_settings()
configure_logging()

@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    if settings.app_env.lower() != "test":
        # Fail startup loudly when Redis is unavailable.
        get_redis_client()
    if not inspect(db_session.engine).has_table("users"):
        yield
    else:
        db = db_session.SessionLocal()
        try:
            seed_local_admin(db)
        finally:
            db.close()
        yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_origin_regex=r"^http://10\.\d{1,3}\.\d{1,3}\.\d{1,3}:3000$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.middleware("http")(request_context_middleware)
app.include_router(tenant_api_router, prefix=settings.api_v1_prefix)
app.include_router(control_plane_api_router, prefix=settings.api_v1_prefix)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    message = exc.detail if isinstance(exc.detail, str) else "Request failed"
    details: dict[str, object] = exc.detail if isinstance(exc.detail, dict) else {}
    payload = exception_envelope(
        request=request,
        status_code=exc.status_code,
        message=message,
        code=f"http_{exc.status_code}",
        details=details,
    )
    return JSONResponse(status_code=exc.status_code, content=payload)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    payload = exception_envelope(
        request=request,
        status_code=422,
        message="Validation failed",
        code="validation_error",
        details={"errors": exc.errors()},
    )
    return JSONResponse(status_code=422, content=payload)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, _exc: Exception) -> JSONResponse:
    payload = exception_envelope(
        request=request,
        status_code=500,
        message="Internal server error",
        code="internal_server_error",
    )
    return JSONResponse(status_code=500, content=payload)
