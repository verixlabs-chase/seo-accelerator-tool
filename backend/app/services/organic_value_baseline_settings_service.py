from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from app.models.organic_value_baseline_setting import OrganicValueBaselineSetting

_MONEY = Decimal("0.01")


def get_settings(db: Session, *, campaign_id: str) -> OrganicValueBaselineSetting | None:
    return (
        db.query(OrganicValueBaselineSetting)
        .filter(OrganicValueBaselineSetting.campaign_id == campaign_id)
        .first()
    )


def upsert_monthly_seo_investment(
    db: Session,
    *,
    campaign_id: str,
    monthly_seo_investment: Decimal,
    updated_by_user_id: str | None,
) -> OrganicValueBaselineSetting:
    row = get_settings(db, campaign_id=campaign_id)
    normalized = Decimal(str(monthly_seo_investment)).quantize(_MONEY, rounding=ROUND_HALF_UP)
    now = datetime.now(UTC)

    if row is None:
        row = OrganicValueBaselineSetting(
            campaign_id=campaign_id,
            monthly_seo_investment=normalized,
            monthly_seo_investment_status="available",
            monthly_seo_investment_source_type="user_provided",
            updated_by_user_id=updated_by_user_id,
            monthly_seo_investment_updated_at=now,
        )
        db.add(row)
    else:
        row.monthly_seo_investment = normalized
        row.monthly_seo_investment_status = "available"
        row.monthly_seo_investment_source_type = "user_provided"
        row.updated_by_user_id = updated_by_user_id
        row.monthly_seo_investment_updated_at = now

    db.commit()
    db.refresh(row)
    return row


def clear_monthly_seo_investment(
    db: Session,
    *,
    campaign_id: str,
    updated_by_user_id: str | None,
) -> OrganicValueBaselineSetting:
    row = get_settings(db, campaign_id=campaign_id)
    now = datetime.now(UTC)

    if row is None:
        row = OrganicValueBaselineSetting(
            campaign_id=campaign_id,
            monthly_seo_investment=None,
            monthly_seo_investment_status="unavailable",
            monthly_seo_investment_source_type="unavailable",
            updated_by_user_id=updated_by_user_id,
            monthly_seo_investment_updated_at=now,
        )
        db.add(row)
    else:
        row.monthly_seo_investment = None
        row.monthly_seo_investment_status = "unavailable"
        row.monthly_seo_investment_source_type = "unavailable"
        row.updated_by_user_id = updated_by_user_id
        row.monthly_seo_investment_updated_at = now

    db.commit()
    db.refresh(row)
    return row
