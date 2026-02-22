from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import distinct, func
from sqlalchemy.orm import Session

from app.models.campaign import Campaign
from app.models.crawl import CrawlPageResult
from app.models.portfolio_usage_daily import PortfolioUsageDaily
from app.models.provider_metric import ProviderExecutionMetric
from app.models.reporting import MonthlyReport


@dataclass(frozen=True)
class PortfolioUsageRollupResult:
    usage_date: date
    inserted_rows: int
    skipped_existing_rows: int


def rollup_portfolio_usage_for_date(*, db: Session, usage_date: date | str) -> PortfolioUsageRollupResult:
    resolved_date = _coerce_date(usage_date)
    day_start = datetime.combine(resolved_date, time.min, tzinfo=UTC)
    day_end = day_start + timedelta(days=1)

    by_portfolio: dict[str, dict[str, int | str | None]] = defaultdict(
        lambda: {
            "organization_id": None,
            "provider_calls": 0,
            "crawl_pages_fetched": 0,
            "reports_generated": 0,
            "active_campaign_days": 0,
        }
    )

    provider_rows = (
        db.query(
            ProviderExecutionMetric.portfolio_id,
            ProviderExecutionMetric.organization_id,
            func.count(ProviderExecutionMetric.id),
        )
        .filter(
            ProviderExecutionMetric.portfolio_id.isnot(None),
            ProviderExecutionMetric.created_at >= day_start,
            ProviderExecutionMetric.created_at < day_end,
        )
        .group_by(ProviderExecutionMetric.portfolio_id, ProviderExecutionMetric.organization_id)
        .all()
    )
    for portfolio_id, organization_id, count_value in provider_rows:
        if portfolio_id is None:
            continue
        row = by_portfolio[str(portfolio_id)]
        row["organization_id"] = row["organization_id"] or organization_id
        row["provider_calls"] = int(count_value or 0)

    crawl_rows = (
        db.query(
            Campaign.portfolio_id,
            Campaign.organization_id,
            func.count(CrawlPageResult.id),
        )
        .join(CrawlPageResult, CrawlPageResult.campaign_id == Campaign.id)
        .filter(
            Campaign.portfolio_id.isnot(None),
            CrawlPageResult.crawled_at >= day_start,
            CrawlPageResult.crawled_at < day_end,
        )
        .group_by(Campaign.portfolio_id, Campaign.organization_id)
        .all()
    )
    for portfolio_id, organization_id, count_value in crawl_rows:
        if portfolio_id is None:
            continue
        row = by_portfolio[str(portfolio_id)]
        row["organization_id"] = row["organization_id"] or organization_id
        row["crawl_pages_fetched"] = int(count_value or 0)

    report_rows = (
        db.query(
            Campaign.portfolio_id,
            Campaign.organization_id,
            func.count(MonthlyReport.id),
        )
        .join(MonthlyReport, MonthlyReport.campaign_id == Campaign.id)
        .filter(
            Campaign.portfolio_id.isnot(None),
            MonthlyReport.generated_at >= day_start,
            MonthlyReport.generated_at < day_end,
        )
        .group_by(Campaign.portfolio_id, Campaign.organization_id)
        .all()
    )
    for portfolio_id, organization_id, count_value in report_rows:
        if portfolio_id is None:
            continue
        row = by_portfolio[str(portfolio_id)]
        row["organization_id"] = row["organization_id"] or organization_id
        row["reports_generated"] = int(count_value or 0)

    active_rows = (
        db.query(
            Campaign.portfolio_id,
            Campaign.organization_id,
            func.count(distinct(Campaign.id)),
        )
        .filter(
            Campaign.portfolio_id.isnot(None),
            func.lower(Campaign.setup_state) == "active",
            Campaign.created_at < day_end,
        )
        .group_by(Campaign.portfolio_id, Campaign.organization_id)
        .all()
    )
    for portfolio_id, organization_id, count_value in active_rows:
        if portfolio_id is None:
            continue
        row = by_portfolio[str(portfolio_id)]
        row["organization_id"] = row["organization_id"] or organization_id
        row["active_campaign_days"] = int(count_value or 0)

    if not by_portfolio:
        return PortfolioUsageRollupResult(
            usage_date=resolved_date,
            inserted_rows=0,
            skipped_existing_rows=0,
        )

    existing_portfolio_ids = {
        str(portfolio_id)
        for portfolio_id, in db.query(PortfolioUsageDaily.portfolio_id).filter(PortfolioUsageDaily.usage_date == resolved_date).all()
    }

    inserted_rows = 0
    skipped_existing_rows = 0
    for portfolio_id, counts in by_portfolio.items():
        if portfolio_id in existing_portfolio_ids:
            skipped_existing_rows += 1
            continue
        db.add(
            PortfolioUsageDaily(
                organization_id=str(counts["organization_id"]) if counts["organization_id"] is not None else None,
                portfolio_id=portfolio_id,
                usage_date=resolved_date,
                provider_calls=int(counts["provider_calls"] or 0),
                crawl_pages_fetched=int(counts["crawl_pages_fetched"] or 0),
                reports_generated=int(counts["reports_generated"] or 0),
                active_campaign_days=int(counts["active_campaign_days"] or 0),
                created_at=datetime.now(UTC),
            )
        )
        inserted_rows += 1

    if inserted_rows > 0:
        db.commit()
    return PortfolioUsageRollupResult(
        usage_date=resolved_date,
        inserted_rows=inserted_rows,
        skipped_existing_rows=skipped_existing_rows,
    )


def rollup_portfolio_usage_incremental(*, db: Session, through_date: date | str | None = None) -> dict:
    last_usage_date = db.query(func.max(PortfolioUsageDaily.usage_date)).scalar()
    start_date = _next_date(last_usage_date) if last_usage_date is not None else _first_rollup_date(db=db)

    if start_date is None:
        return {"status": "noop", "processed_dates": 0, "inserted_rows": 0, "skipped_existing_rows": 0}

    resolved_through_date = _coerce_date(through_date) if through_date is not None else (datetime.now(UTC).date() - timedelta(days=1))
    if start_date > resolved_through_date:
        return {
            "status": "noop",
            "processed_dates": 0,
            "inserted_rows": 0,
            "skipped_existing_rows": 0,
            "start_date": start_date.isoformat(),
            "through_date": resolved_through_date.isoformat(),
        }

    inserted_rows = 0
    skipped_existing_rows = 0
    processed_dates = 0
    cursor = start_date
    while cursor <= resolved_through_date:
        result = rollup_portfolio_usage_for_date(db=db, usage_date=cursor)
        processed_dates += 1
        inserted_rows += result.inserted_rows
        skipped_existing_rows += result.skipped_existing_rows
        cursor = cursor + timedelta(days=1)

    return {
        "status": "ok",
        "processed_dates": processed_dates,
        "inserted_rows": inserted_rows,
        "skipped_existing_rows": skipped_existing_rows,
        "start_date": start_date.isoformat(),
        "through_date": resolved_through_date.isoformat(),
    }


def _first_rollup_date(*, db: Session) -> date | None:
    candidates = [
        db.query(func.min(func.date(ProviderExecutionMetric.created_at)))
        .filter(ProviderExecutionMetric.portfolio_id.isnot(None))
        .scalar(),
        db.query(func.min(func.date(CrawlPageResult.crawled_at)))
        .join(Campaign, Campaign.id == CrawlPageResult.campaign_id)
        .filter(Campaign.portfolio_id.isnot(None))
        .scalar(),
        db.query(func.min(func.date(MonthlyReport.generated_at)))
        .join(Campaign, Campaign.id == MonthlyReport.campaign_id)
        .filter(Campaign.portfolio_id.isnot(None))
        .scalar(),
        db.query(func.min(func.date(Campaign.created_at))).filter(Campaign.portfolio_id.isnot(None)).scalar(),
    ]
    dates = [_coerce_optional_date(value) for value in candidates]
    valid_dates = [value for value in dates if value is not None]
    if not valid_dates:
        return None
    return min(valid_dates)


def _coerce_date(value: date | str) -> date:
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value)).date()


def _coerce_optional_date(value: object) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    return datetime.fromisoformat(str(value)).date()


def _next_date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date() + timedelta(days=1)
    if isinstance(value, date):
        return value + timedelta(days=1)
    return datetime.fromisoformat(str(value)).date() + timedelta(days=1)
