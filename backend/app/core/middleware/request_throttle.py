from __future__ import annotations

import asyncio

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.metrics import active_api_requests, active_api_requests_by_tenant


class RequestThrottleMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, max_concurrent_requests: int = 2000, max_requests_per_tenant: int = 200) -> None:
        super().__init__(app)
        self._max_concurrent_requests = max(1, int(max_concurrent_requests))
        self._max_requests_per_tenant = max(1, int(max_requests_per_tenant))
        self._global_semaphore = asyncio.Semaphore(self._max_concurrent_requests)
        self._tenant_semaphores: dict[str, asyncio.Semaphore] = {}
        self._tenant_lock = asyncio.Lock()

    async def dispatch(self, request: Request, call_next):
        tenant_id = self._tenant_id_for_request(request)
        tenant_semaphore = await self._tenant_semaphore(tenant_id)

        acquired_global = await self._try_acquire(self._global_semaphore)
        if not acquired_global:
            return self._reject('global_concurrency_limit')

        acquired_tenant = await self._try_acquire(tenant_semaphore)
        if not acquired_tenant:
            self._global_semaphore.release()
            return self._reject('tenant_concurrency_limit')

        self._set_metrics(tenant_id)
        try:
            response = await call_next(request)
            return response
        finally:
            tenant_semaphore.release()
            self._global_semaphore.release()
            self._set_metrics(tenant_id)

    async def _tenant_semaphore(self, tenant_id: str) -> asyncio.Semaphore:
        async with self._tenant_lock:
            semaphore = self._tenant_semaphores.get(tenant_id)
            if semaphore is None:
                semaphore = asyncio.Semaphore(self._max_requests_per_tenant)
                self._tenant_semaphores[tenant_id] = semaphore
            return semaphore

    async def _try_acquire(self, semaphore: asyncio.Semaphore) -> bool:
        try:
            await asyncio.wait_for(semaphore.acquire(), timeout=0.001)
        except TimeoutError:
            return False
        return True

    def _tenant_id_for_request(self, request: Request) -> str:
        state_user = getattr(request.state, 'user', None)
        if isinstance(state_user, dict) and state_user.get('tenant_id'):
            return str(state_user['tenant_id'])
        header_tenant = request.headers.get('X-Tenant-Id', '').strip()
        if header_tenant:
            return header_tenant
        path_tenant = request.path_params.get('tenant_id') if hasattr(request, 'path_params') else None
        if path_tenant:
            return str(path_tenant)
        return 'anonymous'

    def _set_metrics(self, tenant_id: str) -> None:
        active_api_requests.set(self._max_concurrent_requests - self._global_semaphore._value)
        active_api_requests_by_tenant.labels(tenant_id=tenant_id).set(
            self._max_requests_per_tenant - self._tenant_semaphores[tenant_id]._value
        )

    def _reject(self, reason: str) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content={
                'message': 'Too many concurrent requests',
                'reason_code': reason,
            },
        )
