from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, computed_field


class ExecutionOut(BaseModel):
    id: str
    recommendation_id: str
    campaign_id: str
    execution_type: str
    execution_payload: str
    idempotency_key: str
    deterministic_hash: str
    status: str
    attempt_count: int
    last_error: str | None
    result_summary: str | None
    executed_at: datetime | None
    created_at: datetime

    model_config = {'from_attributes': True}

    @computed_field(return_type=dict[str, Any])
    def payload(self) -> dict[str, Any]:
        try:
            data = json.loads(self.execution_payload or '{}')
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    @computed_field(return_type=dict[str, Any])
    def result(self) -> dict[str, Any]:
        try:
            data = json.loads(self.result_summary or '{}')
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}


class ExecutionRunIn(BaseModel):
    dry_run: bool = False
