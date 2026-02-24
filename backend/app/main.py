from collections.abc import AsyncIterator
import ast
from contextlib import asynccontextmanager
import json
import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from sqlalchemy import inspect

from app.api.response import exception_envelope
from app.api.v1 import google_oauth
from app.api.v1.router import control_plane_api_router, tenant_api_router
from app.core.config import get_settings
from app.core.logging_config import configure_logging
from app.core.metrics import render_metrics
from app.core.middleware import (
    MetricsMiddleware,
    RateLimitMiddleware,
    RequestLoggingMiddleware,
    RequestSizeLimitMiddleware,
    SecurityHeadersMiddleware,
)
from app.core.tracing import setup_tracing
from app.db.redis_client import get_redis_client
import app.db.session as db_session
from app.services.auth_service import seed_local_admin

settings = get_settings()
configure_logging(log_level=settings.log_level, app_env=settings.app_env)
logger = logging.getLogger("lsos.api")
logger.info("Secrets loaded from environment (production-safe mode enabled).")


def _parse_worker_count() -> int:
    for env_name in ("UVICORN_WORKERS", "WEB_CONCURRENCY"):
        raw = os.getenv(env_name, "").strip()
        if raw:
            try:
                return max(1, int(raw))
            except ValueError:
                return 1
    return 1


def _find_module_level_mutables(path: Path) -> list[int]:
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return []
    tree = ast.parse(source)
    matches: list[int] = []
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            value = node.value
            if isinstance(value, (ast.Dict, ast.Set, ast.List)):
                matches.append(node.lineno)
                continue
            if isinstance(value, ast.Call):
                func_name = getattr(value.func, "id", None)
                if func_name in {"dict", "set", "list", "defaultdict", "OrderedDict"}:
                    matches.append(node.lineno)
    return matches


def _emit_statelessness_warnings() -> None:
    worker_count = _parse_worker_count()
    if worker_count <= 1 and settings.app_env.lower() != "production":
        return
    base_dir = Path(__file__).resolve().parent
    files_to_audit = [
        base_dir / "core" / "middleware" / "rate_limit.py",
        base_dir / "core" / "metrics.py",
        base_dir / "services" / "google_oauth_service.py",
        base_dir / "core" / "crypto.py",
    ]
    for file_path in files_to_audit:
        lines = _find_module_level_mutables(file_path)
        if not lines:
            continue
        logger.warning(
            json.dumps(
                {
                    "event": "statelessness_guard_warning",
                    "file": str(file_path),
                    "lines": lines,
                    "workers": worker_count,
                    "app_env": settings.app_env,
                }
            )
        )


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    _emit_statelessness_warnings()
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
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(RequestSizeLimitMiddleware, max_request_body_bytes=settings.max_request_body_bytes)
app.add_middleware(
    RateLimitMiddleware,
    enabled=settings.rate_limit_enabled,
    requests_per_minute=settings.rate_limit_requests_per_minute,
    redis_url=settings.redis_url,
)
app.add_middleware(MetricsMiddleware)
app.add_middleware(SecurityHeadersMiddleware, app_env=settings.app_env)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_origin_regex=r"^http://10\.\d{1,3}\.\d{1,3}\.\d{1,3}:3000$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
setup_tracing(app, otel_exporter_endpoint=settings.otel_exporter_endpoint)
app.include_router(tenant_api_router, prefix=settings.api_v1_prefix)
app.include_router(control_plane_api_router, prefix=settings.api_v1_prefix)
app.include_router(google_oauth.public_router, prefix=settings.api_v1_prefix)

if settings.metrics_enabled:
    @app.get("/metrics", include_in_schema=False)
    async def metrics(request: Request) -> Response:
        if settings.metrics_require_auth:
            client_ip = request.client.host if request.client is not None and request.client.host else ""
            allowed_ips = {ip.strip() for ip in settings.metrics_allowed_ips.split(",") if ip.strip()}
            header_token = request.headers.get("X-Metrics-Token", "")
            expected_token = os.getenv("METRICS_TOKEN", "").strip()
            ip_allowed = client_ip in allowed_ips
            token_allowed = bool(expected_token) and header_token == expected_token
            if not ip_allowed and not token_allowed:
                return JSONResponse(
                    status_code=403,
                    content={"message": "Forbidden", "reason_code": "metrics_forbidden"},
                )
        payload, content_type = render_metrics()
        return Response(content=payload, media_type=content_type)


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
