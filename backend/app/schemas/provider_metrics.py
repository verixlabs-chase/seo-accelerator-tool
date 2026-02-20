from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ProviderExecutionMetricOut(BaseModel):
    id: str
    tenant_id: str
    sub_account_id: str | None
    environment: str
    task_execution_id: str | None
    provider_name: str
    provider_version: str | None
    capability: str
    operation: str
    idempotency_key: str
    correlation_id: str | None
    attempt_number: int
    max_attempts: int
    duration_ms: int
    timeout_budget_ms: int
    outcome: str
    reason_code: str | None
    error_severity: str | None
    retryable: bool
    http_status: int | None
    created_at: datetime

    model_config = {"from_attributes": True}
