from __future__ import annotations

from collections import defaultdict

from sqlalchemy.orm import Session

from app.models.business_location import BusinessLocation
from app.models.campaign import Campaign
from app.models.campaign_daily_metric import CampaignDailyMetric
from app.models.location import Location
from app.models.sub_account import SubAccount


def build_account_hierarchy(db: Session, *, organization_id: str) -> dict[str, object]:
    subaccounts = (
        db.query(SubAccount)
        .filter(SubAccount.organization_id == organization_id)
        .order_by(SubAccount.created_at.asc(), SubAccount.id.asc())
        .all()
    )
    business_locations = (
        db.query(BusinessLocation)
        .filter(BusinessLocation.organization_id == organization_id)
        .order_by(BusinessLocation.created_at.asc(), BusinessLocation.id.asc())
        .all()
    )
    execution_locations = (
        db.query(Location)
        .filter(Location.organization_id == organization_id)
        .order_by(Location.created_at.asc(), Location.id.asc())
        .all()
    )
    campaigns = (
        db.query(Campaign)
        .filter(Campaign.organization_id == organization_id)
        .order_by(Campaign.created_at.asc(), Campaign.id.asc())
        .all()
    )
    metric_rows = (
        db.query(CampaignDailyMetric)
        .filter(CampaignDailyMetric.organization_id == organization_id)
        .order_by(
            CampaignDailyMetric.campaign_id.asc(),
            CampaignDailyMetric.metric_date.desc(),
            CampaignDailyMetric.id.desc(),
        )
        .all()
    )
    latest_metric_by_campaign: dict[str, CampaignDailyMetric] = {}
    for row in metric_rows:
        latest_metric_by_campaign.setdefault(row.campaign_id, row)

    locations_by_business_location: dict[str, list[Location]] = defaultdict(list)
    campaigns_by_business_location: dict[str, list[Campaign]] = defaultdict(list)
    for row in execution_locations:
        if row.business_location_id:
            locations_by_business_location[row.business_location_id].append(row)
    for row in campaigns:
        if row.business_location_id:
            campaigns_by_business_location[row.business_location_id].append(row)

    business_locations_by_subaccount: dict[str, list[BusinessLocation]] = defaultdict(list)
    for row in business_locations:
        if row.sub_account_id:
            business_locations_by_subaccount[row.sub_account_id].append(row)

    subaccount_items: list[dict[str, object]] = []
    for subaccount in subaccounts:
        scoped_business_locations = business_locations_by_subaccount.get(subaccount.id, [])
        scoped_campaigns = [row for row in campaigns if row.sub_account_id == subaccount.id]
        subaccount_items.append(
            {
                "id": subaccount.id,
                "name": subaccount.name,
                "status": subaccount.status,
                "created_at": subaccount.created_at,
                "business_locations": [
                    _business_location_payload(
                        row,
                        execution_locations=locations_by_business_location.get(row.id, []),
                        campaigns=campaigns_by_business_location.get(row.id, []),
                        latest_metric_by_campaign=latest_metric_by_campaign,
                    )
                    for row in scoped_business_locations
                ],
                "unassigned_campaigns": [
                    _campaign_payload(
                        row,
                        latest_metric=latest_metric_by_campaign.get(row.id),
                    )
                    for row in scoped_campaigns
                    if row.business_location_id is None
                ],
                "counts": {
                    "business_locations": len(scoped_business_locations),
                    "campaigns": len(scoped_campaigns),
                    "execution_locations": sum(
                        len(locations_by_business_location.get(row.id, []))
                        for row in scoped_business_locations
                    ),
                },
            }
        )

    orphan_business_locations = [
        row for row in business_locations if row.sub_account_id is None
    ]
    unassigned_execution_locations = [
        _location_payload(row)
        for row in execution_locations
        if row.business_location_id is None
    ]
    unassigned_campaigns = [
        _campaign_payload(
            row,
            latest_metric=latest_metric_by_campaign.get(row.id),
        )
        for row in campaigns
        if row.business_location_id is None and row.sub_account_id is None
    ]

    integrity_issues = _integrity_issues(
        business_locations=business_locations,
        execution_locations=execution_locations,
        campaigns=campaigns,
    )
    return {
        "organization_id": organization_id,
        "subaccounts": subaccount_items,
        "unassigned": {
            "business_locations": [
                _business_location_payload(
                    row,
                    execution_locations=locations_by_business_location.get(row.id, []),
                    campaigns=campaigns_by_business_location.get(row.id, []),
                    latest_metric_by_campaign=latest_metric_by_campaign,
                )
                for row in orphan_business_locations
            ],
            "execution_locations": unassigned_execution_locations,
            "campaigns": unassigned_campaigns,
        },
        "totals": {
            "subaccounts": len(subaccounts),
            "business_locations": len(business_locations),
            "execution_locations": len(execution_locations),
            "campaigns": len(campaigns),
            "active_business_locations": sum(
                1 for row in business_locations if row.status == "active"
            ),
            "unassigned_business_locations": len(orphan_business_locations),
            "integrity_issues": len(integrity_issues),
        },
        "integrity_issues": integrity_issues,
    }


def _business_location_payload(
    row: BusinessLocation,
    *,
    execution_locations: list[Location],
    campaigns: list[Campaign],
    latest_metric_by_campaign: dict[str, CampaignDailyMetric],
) -> dict[str, object]:
    latest_metrics = [
        latest_metric_by_campaign[row.id]
        for row in campaigns
        if row.id in latest_metric_by_campaign
    ]
    return {
        "id": row.id,
        "sub_account_id": row.sub_account_id,
        "name": row.name,
        "domain": row.domain,
        "primary_city": row.primary_city,
        "city": row.city,
        "region": row.region,
        "country_code": row.country_code,
        "address_line1": row.address_line1,
        "postal_code": row.postal_code,
        "latitude": float(row.latitude) if row.latitude is not None else None,
        "longitude": float(row.longitude) if row.longitude is not None else None,
        "coordinate_precision": row.coordinate_precision,
        "coordinate_source": row.coordinate_source,
        "provider_location_code": row.provider_location_code,
        "provider_location_name": row.provider_location_name,
        "provider_location_type": row.provider_location_type,
        "provider_location_resolved_at": row.provider_location_resolved_at,
        "status": row.status,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "execution_locations": [_location_payload(item) for item in execution_locations],
        "campaigns": [
            _campaign_payload(
                item,
                latest_metric=latest_metric_by_campaign.get(item.id),
            )
            for item in campaigns
        ],
        "performance": _location_performance_payload(latest_metrics),
    }


def _location_payload(row: Location) -> dict[str, object]:
    status_value = row.status.value if hasattr(row.status, "value") else str(row.status)
    return {
        "id": row.id,
        "sub_account_id": row.sub_account_id,
        "business_location_id": row.business_location_id,
        "campaign_id": row.campaign_id,
        "portfolio_id": row.portfolio_id,
        "location_code": row.location_code,
        "name": row.name,
        "country_code": row.country_code,
        "region": row.region,
        "city": row.city,
        "lat": float(row.lat) if row.lat is not None else None,
        "lng": float(row.lng) if row.lng is not None else None,
        "status": status_value,
    }


def _campaign_payload(
    row: Campaign,
    *,
    latest_metric: CampaignDailyMetric | None = None,
) -> dict[str, object]:
    return {
        "id": row.id,
        "sub_account_id": row.sub_account_id,
        "business_location_id": row.business_location_id,
        "portfolio_id": row.portfolio_id,
        "name": row.name,
        "domain": row.domain,
        "setup_state": row.setup_state,
        "month_number": row.month_number,
        "latest_metric": _metric_payload(latest_metric) if latest_metric else None,
    }


def _metric_payload(row: CampaignDailyMetric) -> dict[str, object]:
    return {
        "metric_date": row.metric_date,
        "clicks": row.clicks,
        "impressions": row.impressions,
        "avg_position": row.avg_position,
        "sessions": row.sessions,
        "conversions": row.conversions,
        "technical_issue_count": row.technical_issue_count,
        "intelligence_score": row.intelligence_score,
        "reviews_last_30d": row.reviews_last_30d,
        "avg_rating_last_30d": row.avg_rating_last_30d,
    }


def _location_performance_payload(
    rows: list[CampaignDailyMetric],
) -> dict[str, object]:
    positions = [float(row.avg_position) for row in rows if row.avg_position is not None]
    intelligence_scores = [
        float(row.intelligence_score)
        for row in rows
        if row.intelligence_score is not None
    ]
    ratings = [
        float(row.avg_rating_last_30d)
        for row in rows
        if row.avg_rating_last_30d is not None
    ]
    return {
        "data_available": bool(rows),
        "campaigns_with_data": len(rows),
        "as_of": max((row.metric_date for row in rows), default=None),
        "clicks": sum(int(row.clicks or 0) for row in rows),
        "impressions": sum(int(row.impressions or 0) for row in rows),
        "avg_position": round(sum(positions) / len(positions), 2) if positions else None,
        "sessions": sum(int(row.sessions or 0) for row in rows),
        "conversions": sum(int(row.conversions or 0) for row in rows),
        "technical_issue_count": sum(int(row.technical_issue_count or 0) for row in rows),
        "intelligence_score": (
            round(sum(intelligence_scores) / len(intelligence_scores), 2)
            if intelligence_scores
            else None
        ),
        "reviews_last_30d": sum(int(row.reviews_last_30d or 0) for row in rows),
        "avg_rating_last_30d": round(sum(ratings) / len(ratings), 2) if ratings else None,
    }


def _integrity_issues(
    *,
    business_locations: list[BusinessLocation],
    execution_locations: list[Location],
    campaigns: list[Campaign],
) -> list[dict[str, str]]:
    business_location_map = {row.id: row for row in business_locations}
    issues: list[dict[str, str]] = []
    for row in execution_locations:
        business_location = business_location_map.get(str(row.business_location_id))
        if business_location is None:
            continue
        if (
            business_location.sub_account_id is not None
            and row.sub_account_id != business_location.sub_account_id
        ):
            issues.append(
                {
                    "entity_type": "execution_location",
                    "entity_id": row.id,
                    "reason_code": "subaccount_mismatch",
                }
            )
    for row in campaigns:
        business_location = business_location_map.get(str(row.business_location_id))
        if business_location is None:
            continue
        if (
            business_location.sub_account_id is not None
            and row.sub_account_id != business_location.sub_account_id
        ):
            issues.append(
                {
                    "entity_type": "campaign",
                    "entity_id": row.id,
                    "reason_code": "subaccount_mismatch",
                }
            )
    return issues
