from __future__ import annotations

from datetime import UTC, datetime, timedelta
from math import ceil

from sqlalchemy.orm import Session

from app.models.provider_metric import ProviderExecutionMetric


FAILURE_OUTCOMES = {"failed", "dead_letter"}


def build_subaccount_dashboard(
    db: Session,
    *,
    tenant_id: str,
    sub_account_id: str,
    window_days: int = 30,
) -> dict:
    now = datetime.now(UTC)
    window_start = now - timedelta(days=window_days)

    rows = (
        db.query(ProviderExecutionMetric)
        .filter(
            ProviderExecutionMetric.tenant_id == tenant_id,
            ProviderExecutionMetric.sub_account_id == sub_account_id,
            ProviderExecutionMetric.created_at >= window_start,
            ProviderExecutionMetric.created_at <= now,
        )
        .order_by(ProviderExecutionMetric.created_at.desc(), ProviderExecutionMetric.id.desc())
        .all()
    )

    total_calls = len(rows)
    success_count = sum(1 for row in rows if row.outcome == "success")
    retry_count = sum(1 for row in rows if row.outcome == "retry")
    failed_count = sum(1 for row in rows if row.outcome == "failed")
    dead_letter_count = sum(1 for row in rows if row.outcome == "dead_letter")

    success_rate_percent = round((success_count / total_calls) * 100.0, 2) if total_calls > 0 else 0.0
    p95_latency_ms = _p95([int(row.duration_ms) for row in rows])

    failure_rows = [row for row in rows if row.outcome in FAILURE_OUTCOMES]
    provider_failure_counts: dict[str, int] = {}
    capability_failure_counts: dict[str, int] = {}
    for row in failure_rows:
        provider_failure_counts[row.provider_name] = provider_failure_counts.get(row.provider_name, 0) + 1
        capability_failure_counts[row.capability] = capability_failure_counts.get(row.capability, 0) + 1

    top_failing_provider = _top_key_by_count(provider_failure_counts)
    top_failing_capability = _top_key_by_count(capability_failure_counts)

    last_10_failures = [
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
    ]

    return {
        "sub_account_id": sub_account_id,
        "window": {"days": window_days, "from": window_start.isoformat(), "to": now.isoformat()},
        "metrics": {
            "total_calls": total_calls,
            "success_count": success_count,
            "retry_count": retry_count,
            "failed_count": failed_count,
            "dead_letter_count": dead_letter_count,
            "success_rate_percent": success_rate_percent,
            "p95_latency_ms": p95_latency_ms,
            "top_failing_provider": top_failing_provider,
            "top_failing_capability": top_failing_capability,
            "last_10_failures": last_10_failures,
        },
    }


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
