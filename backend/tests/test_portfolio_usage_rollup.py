from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from app.models.campaign import Campaign
from app.models.crawl import CrawlPageResult, CrawlRun, Page
from app.models.organization import Organization
from app.models.portfolio import Portfolio
from app.models.portfolio_usage_daily import PortfolioUsageDaily
from app.models.provider_metric import ProviderExecutionMetric
from app.models.reporting import MonthlyReport
from app.services import portfolio_usage_service
from app.tasks import tasks


def _seed_org_and_portfolio(db_session, *, org_id: str, portfolio_id: str) -> None:
    now = datetime.now(UTC)
    db_session.add(
        Organization(
            id=org_id,
            name=f"Org-{org_id[:8]}",
            plan_type="standard",
            billing_mode="subscription",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    db_session.add(
        Portfolio(
            id=portfolio_id,
            organization_id=org_id,
            name=f"Portfolio-{portfolio_id[:8]}",
            code=f"portfolio-{portfolio_id[:8]}",
            status="active",
            timezone="UTC",
            default_sla_tier="standard",
            created_at=now,
            updated_at=now,
        )
    )
    db_session.flush()


def _seed_campaign(db_session, *, org_id: str, portfolio_id: str, created_at: datetime, setup_state: str = "Active") -> Campaign:
    campaign = Campaign(
        id=str(uuid.uuid4()),
        tenant_id=org_id,
        organization_id=org_id,
        portfolio_id=portfolio_id,
        name=f"Campaign-{uuid.uuid4().hex[:8]}",
        domain="usage-rollup.example",
        month_number=1,
        setup_state=setup_state,
        created_at=created_at,
    )
    db_session.add(campaign)
    db_session.flush()
    return campaign


def _seed_provider_metric(db_session, *, org_id: str, portfolio_id: str, created_at: datetime, suffix: str) -> None:
    db_session.add(
        ProviderExecutionMetric(
            tenant_id=org_id,
            organization_id=org_id,
            portfolio_id=portfolio_id,
            sub_account_id=None,
            campaign_id=None,
            environment="production",
            task_execution_id=None,
            provider_name="google_search_console",
            provider_version="1.0.0",
            capability="search_console_analytics",
            operation="search_console_query",
            idempotency_key=f"idem-{portfolio_id}-{suffix}",
            correlation_id=f"corr-{suffix}",
            attempt_number=1,
            max_attempts=3,
            duration_ms=120,
            timeout_budget_ms=5000,
            outcome="success",
            reason_code=None,
            error_severity=None,
            retryable=False,
            http_status=200,
            created_at=created_at,
        )
    )


def _seed_crawl_result(db_session, *, campaign: Campaign, crawled_at: datetime, suffix: str) -> None:
    page = Page(
        id=str(uuid.uuid4()),
        tenant_id=campaign.tenant_id,
        campaign_id=campaign.id,
        url=f"https://usage-rollup.example/{suffix}",
        last_crawled_at=crawled_at,
        created_at=crawled_at,
    )
    run = CrawlRun(
        id=str(uuid.uuid4()),
        tenant_id=campaign.tenant_id,
        campaign_id=campaign.id,
        crawl_type="deep",
        status="complete",
        seed_url="https://usage-rollup.example",
        pages_discovered=1,
        created_at=crawled_at,
        started_at=crawled_at,
        finished_at=crawled_at,
    )
    db_session.add(page)
    db_session.add(run)
    db_session.flush()
    db_session.add(
        CrawlPageResult(
            id=str(uuid.uuid4()),
            tenant_id=campaign.tenant_id,
            campaign_id=campaign.id,
            crawl_run_id=run.id,
            page_id=page.id,
            status_code=200,
            is_indexable=1,
            title=f"Page {suffix}",
            crawled_at=crawled_at,
        )
    )


def _seed_report(db_session, *, campaign: Campaign, generated_at: datetime, month_number: int) -> None:
    db_session.add(
        MonthlyReport(
            id=str(uuid.uuid4()),
            tenant_id=campaign.tenant_id,
            campaign_id=campaign.id,
            month_number=month_number,
            report_status="generated",
            summary_json="{}",
            generated_at=generated_at,
        )
    )


def test_rollup_for_date_tracks_all_usage_dimensions(db_session) -> None:
    org_id = str(uuid.uuid4())
    portfolio_id = str(uuid.uuid4())
    _seed_org_and_portfolio(db_session, org_id=org_id, portfolio_id=portfolio_id)

    target_day = date(2026, 2, 22)
    inside = datetime(2026, 2, 22, 12, 0, tzinfo=UTC)
    outside = inside + timedelta(days=1)
    campaign = _seed_campaign(db_session, org_id=org_id, portfolio_id=portfolio_id, created_at=inside - timedelta(days=3))

    _seed_provider_metric(db_session, org_id=org_id, portfolio_id=portfolio_id, created_at=inside, suffix="p1")
    _seed_provider_metric(db_session, org_id=org_id, portfolio_id=portfolio_id, created_at=inside + timedelta(minutes=5), suffix="p2")
    _seed_provider_metric(db_session, org_id=org_id, portfolio_id=portfolio_id, created_at=outside, suffix="p-outside")

    _seed_crawl_result(db_session, campaign=campaign, crawled_at=inside, suffix="crawl-1")
    _seed_crawl_result(db_session, campaign=campaign, crawled_at=inside + timedelta(minutes=2), suffix="crawl-2")
    _seed_crawl_result(db_session, campaign=campaign, crawled_at=inside + timedelta(minutes=4), suffix="crawl-3")

    _seed_report(db_session, campaign=campaign, generated_at=inside, month_number=1)
    db_session.commit()

    result = portfolio_usage_service.rollup_portfolio_usage_for_date(db=db_session, usage_date=target_day)
    assert result.inserted_rows == 1
    assert result.skipped_existing_rows == 0

    row = (
        db_session.query(PortfolioUsageDaily)
        .filter(PortfolioUsageDaily.portfolio_id == portfolio_id, PortfolioUsageDaily.usage_date == target_day)
        .first()
    )
    assert row is not None
    assert row.provider_calls == 2
    assert row.crawl_pages_fetched == 3
    assert row.reports_generated == 1
    assert row.active_campaign_days == 1


def test_rollup_is_append_only_and_idempotent(db_session) -> None:
    org_id = str(uuid.uuid4())
    portfolio_id = str(uuid.uuid4())
    _seed_org_and_portfolio(db_session, org_id=org_id, portfolio_id=portfolio_id)

    target_day = date(2026, 2, 23)
    inside = datetime(2026, 2, 23, 9, 0, tzinfo=UTC)
    _seed_campaign(db_session, org_id=org_id, portfolio_id=portfolio_id, created_at=inside - timedelta(days=1))
    _seed_provider_metric(db_session, org_id=org_id, portfolio_id=portfolio_id, created_at=inside, suffix="first")
    db_session.commit()

    first = portfolio_usage_service.rollup_portfolio_usage_for_date(db=db_session, usage_date=target_day)
    second = portfolio_usage_service.rollup_portfolio_usage_for_date(db=db_session, usage_date=target_day)

    assert first.inserted_rows == 1
    assert second.inserted_rows == 0
    assert second.skipped_existing_rows == 1
    assert (
        db_session.query(PortfolioUsageDaily)
        .filter(PortfolioUsageDaily.portfolio_id == portfolio_id, PortfolioUsageDaily.usage_date == target_day)
        .count()
        == 1
    )


def test_incremental_rollup_task_is_idempotent(db_session) -> None:
    org_id = str(uuid.uuid4())
    portfolio_id = str(uuid.uuid4())
    _seed_org_and_portfolio(db_session, org_id=org_id, portfolio_id=portfolio_id)

    day_one = datetime(2026, 2, 20, 8, 0, tzinfo=UTC)
    day_two = datetime(2026, 2, 21, 8, 0, tzinfo=UTC)
    campaign = _seed_campaign(db_session, org_id=org_id, portfolio_id=portfolio_id, created_at=day_one)
    _seed_provider_metric(db_session, org_id=org_id, portfolio_id=portfolio_id, created_at=day_one, suffix="inc-1")
    _seed_provider_metric(db_session, org_id=org_id, portfolio_id=portfolio_id, created_at=day_two, suffix="inc-2")
    _seed_crawl_result(db_session, campaign=campaign, crawled_at=day_two, suffix="inc-crawl")
    _seed_report(db_session, campaign=campaign, generated_at=day_two, month_number=2)
    db_session.commit()

    first = tasks.portfolio_usage_rollup_incremental.run(through_date="2026-02-21")
    second = tasks.portfolio_usage_rollup_incremental.run(through_date="2026-02-21")

    assert first["status"] == "ok"
    assert first["processed_dates"] == 2
    assert first["inserted_rows"] == 2
    assert second["status"] == "noop"
    assert (
        db_session.query(PortfolioUsageDaily)
        .filter(PortfolioUsageDaily.portfolio_id == portfolio_id)
        .count()
        == 2
    )
