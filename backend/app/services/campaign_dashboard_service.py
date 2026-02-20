from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from math import ceil

from sqlalchemy.orm import Session

from app.models.provider_metric import ProviderExecutionMetric
from app.models.task_execution import TaskExecution


FAILURE_OUTCOMES = {"failed", "dead_letter"}


def build_campaign_dashboard(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> dict:
    window_end = _as_utc(date_to) or datetime.now(UTC)
    window_start = _as_utc(date_from) or (window_end - timedelta(days=30))

    base_rows = (
        db.query(ProviderExecutionMetric)
        .filter(
            ProviderExecutionMetric.tenant_id == tenant_id,
            ProviderExecutionMetric.created_at >= window_start,
            ProviderExecutionMetric.created_at <= window_end,
        )
        .order_by(ProviderExecutionMetric.created_at.desc(), ProviderExecutionMetric.id.desc())
        .all()
    )

    task_ids = list({row.task_execution_id for row in base_rows if row.task_execution_id is not None})
    campaign_by_task_id: dict[str, str] = {}
    if task_ids:
        task_rows = (
            db.query(TaskExecution)
            .filter(
                TaskExecution.tenant_id == tenant_id,
                TaskExecution.id.in_(task_ids),
            )
            .all()
        )
        campaign_by_task_id = {row.id: _campaign_id_from_payload(row.payload_json) for row in task_rows}

    rows = [
        row
        for row in base_rows
        if row.task_execution_id is not None and campaign_by_task_id.get(row.task_execution_id) == campaign_id
    ]

    total_calls = len(rows)
    success_count = sum(1 for row in rows if row.outcome == "success")
    retry_count = sum(1 for row in rows if row.outcome == "retry")
    failed_count = sum(1 for row in rows if row.outcome == "failed")
    dead_letter_count = sum(1 for row in rows if row.outcome == "dead_letter")
    success_rate_percent = round((success_count / total_calls) * 100.0, 2) if total_calls > 0 else 0.0

    failure_rows = [row for row in rows if row.outcome in FAILURE_OUTCOMES]
    provider_failure_counts: dict[str, int] = {}
    capability_failure_counts: dict[str, int] = {}
    for row in failure_rows:
        provider_failure_counts[row.provider_name] = provider_failure_counts.get(row.provider_name, 0) + 1
        capability_failure_counts[row.capability] = capability_failure_counts.get(row.capability, 0) + 1

    return {
        "campaign_id": campaign_id,
        "window": {"date_from": window_start.isoformat(), "date_to": window_end.isoformat()},
        "metrics": {
            "total_calls": total_calls,
            "success_count": success_count,
            "retry_count": retry_count,
            "failed_count": failed_count,
            "dead_letter_count": dead_letter_count,
            "success_rate_percent": success_rate_percent,
            "p95_latency_ms": _p95([int(row.duration_ms) for row in rows]),
            "top_failing_provider": _top_key_by_count(provider_failure_counts),
            "top_failing_capability": _top_key_by_count(capability_failure_counts),
            "last_10_failures": [
                {
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "provider_name": row.provider_name,
                    "capability": row.capability,
                    "outcome": row.outcome,
                    "reason_code": row.reason_code,
                    "attempt_number": row.attempt_number,
                    "duration_ms": row.duration_ms,
                    "correlation_id": row.correlation_id,
                }
                for row in failure_rows[:10]
            ],
            "last_10_failures_pagination": {
                "limit": 10,
                "returned": min(10, len(failure_rows)),
                "total_failures": len(failure_rows),
                "has_more": len(failure_rows) > 10,
            },
        },
    }


def _campaign_id_from_payload(payload_json: str) -> str:
    try:
        payload = json.loads(payload_json)
    except Exception:  # noqa: BLE001
        return ""
    if not isinstance(payload, dict):
        return ""
    campaign_id = payload.get("campaign_id")
    return campaign_id if isinstance(campaign_id, str) else ""


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _p95(values: list[int]) -> int | None:
    if not values:
        return None
    sorted_values = sorted(values)
    rank = max(1, ceil(0.95 * len(sorted_values)))
    return sorted_values[rank - 1]


def _top_key_by_count(counts: dict[str, int]) -> str | None:
    if not counts:
        return None
    return max(counts.items(), key=lambda item: (item[1], item[0]))[0]
