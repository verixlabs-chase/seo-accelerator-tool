from datetime import UTC, datetime, timedelta

from app.models.provider_health import ProviderHealthState
from app.models.provider_metric import ProviderExecutionMetric
from app.models.provider_quota import ProviderQuotaState
from app.models.tenant import Tenant
from app.services.provider_telemetry_service import ProviderTelemetryService


def test_provider_telemetry_persistence(db_session) -> None:
    tenant = db_session.query(Tenant).first()
    assert tenant is not None

    telemetry = ProviderTelemetryService(db_session)
    telemetry.record_execution_metric(
        tenant_id=tenant.id,
        sub_account_id="sub-1",
        campaign_id="campaign-1",
        provider_name="rank",
        provider_version="1.0.0",
        capability="rank_snapshot",
        operation="not_in_vocab",
        idempotency_key="k-1",
        correlation_id="c-1",
        attempt_number=1,
        max_attempts=3,
        duration_ms=120,
        timeout_budget_ms=30000,
        outcome="success",
        reason_code=None,
        error_severity=None,
        retryable=False,
    )
    telemetry.upsert_health_state(
        tenant_id=tenant.id,
        provider_name="rank",
        provider_version="1.0.0",
        capability="rank_snapshot",
        breaker_state="closed",
        consecutive_failures=0,
        success_rate_1h=0.99,
        p95_latency_ms_1h=250,
        last_error_code=None,
        last_error_at=None,
        last_success_at=datetime.now(UTC),
    )
    telemetry.upsert_quota_state(
        tenant_id=tenant.id,
        provider_name="rank",
        capability="rank_snapshot",
        window_start=datetime.now(UTC),
        window_end=datetime.now(UTC) + timedelta(hours=1),
        limit_count=1000,
        used_count=100,
        remaining_count=900,
        last_exhausted_at=None,
    )

    metric = db_session.query(ProviderExecutionMetric).one()
    health = db_session.query(ProviderHealthState).one()
    quota = db_session.query(ProviderQuotaState).one()

    assert metric.provider_name == "rank"
    assert metric.sub_account_id == "sub-1"
    assert metric.campaign_id == "campaign-1"
    assert metric.operation == "unknown"
    assert health.capability == "rank_snapshot"
    assert quota.remaining_count == 900


def test_provider_telemetry_failures_are_non_blocking(db_session, monkeypatch) -> None:
    tenant = db_session.query(Tenant).first()
    assert tenant is not None

    telemetry = ProviderTelemetryService(db_session)

    def _raise_commit() -> None:
        raise RuntimeError("db failure")

    monkeypatch.setattr(db_session, "commit", _raise_commit)

    telemetry.record_execution_metric(
        tenant_id=tenant.id,
        provider_name="rank",
        capability="rank_snapshot",
        operation="snapshot",
        idempotency_key="k-2",
        attempt_number=1,
        max_attempts=1,
        duration_ms=10,
        timeout_budget_ms=30000,
        outcome="failed",
        retryable=False,
    )
    telemetry.upsert_health_state(
        tenant_id=tenant.id,
        provider_name="rank",
        capability="rank_snapshot",
        breaker_state="open",
        consecutive_failures=1,
    )
    telemetry.upsert_quota_state(
        tenant_id=tenant.id,
        provider_name="rank",
        capability="rank_snapshot",
        window_start=datetime.now(UTC),
        window_end=datetime.now(UTC) + timedelta(minutes=10),
        limit_count=10,
        used_count=1,
        remaining_count=9,
    )
