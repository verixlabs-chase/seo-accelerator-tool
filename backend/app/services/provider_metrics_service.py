from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.provider_metric import ProviderExecutionMetric


@dataclass(frozen=True)
class ProviderMetricQuery:
    tenant_id: str
    provider_name: str | None = None
    capability: str | None = None
    outcome: str | None = None
    sub_account_id: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    limit: int = 50
    offset: int = 0


class ProviderMetricsService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def list_execution_metrics(self, query: ProviderMetricQuery) -> tuple[list[ProviderExecutionMetric], int]:
        rows_query = self._db.query(ProviderExecutionMetric).filter(ProviderExecutionMetric.tenant_id == query.tenant_id)

        if query.provider_name is not None:
            rows_query = rows_query.filter(ProviderExecutionMetric.provider_name == query.provider_name)
        if query.capability is not None:
            rows_query = rows_query.filter(ProviderExecutionMetric.capability == query.capability)
        if query.outcome is not None:
            rows_query = rows_query.filter(ProviderExecutionMetric.outcome == query.outcome)
        if query.sub_account_id is not None:
            rows_query = rows_query.filter(ProviderExecutionMetric.sub_account_id == query.sub_account_id)
        if query.date_from is not None:
            rows_query = rows_query.filter(ProviderExecutionMetric.created_at >= self._as_utc(query.date_from))
        if query.date_to is not None:
            rows_query = rows_query.filter(ProviderExecutionMetric.created_at <= self._as_utc(query.date_to))

        total = rows_query.count()
        rows = (
            rows_query.order_by(ProviderExecutionMetric.created_at.desc(), ProviderExecutionMetric.id.desc())
            .offset(query.offset)
            .limit(query.limit)
            .all()
        )
        return rows, total

    def _as_utc(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
