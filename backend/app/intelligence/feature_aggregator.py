from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.intelligence.feature_store import compute_features
from app.models.campaign import Campaign
from app.models.content import ContentAsset
from app.models.crawl import CrawlPageResult
from app.models.rank import CampaignKeyword
from app.models.temporal import TemporalSignalSnapshot

_FEATURE_METRICS = {
    'technical_issue_density',
    'internal_link_ratio',
    'ranking_velocity',
    'content_growth_rate',
    'crawl_health_score',
}


def aggregate_features(db: Session, campaign_ids: list[str] | None = None) -> list[dict[str, Any]]:
    campaigns = _campaigns_for_aggregation(db, campaign_ids)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for campaign in campaigns:
        cohort_context = describe_campaign_cohort(db, campaign.id)
        feature_values = _latest_feature_values(db, campaign.id)
        if not feature_values:
            feature_values = compute_features(campaign.id, db=db, persist=False)

        grouped[cohort_context['cohort']].append(
            {
                'campaign_id': campaign.id,
                'cohort_context': cohort_context,
                'features': feature_values,
                'content_pages': float(_published_content_count(db, campaign.id)),
            }
        )

    rows: list[dict[str, Any]] = []
    for cohort_key in sorted(grouped):
        records = grouped[cohort_key]
        count = max(1, len(records))

        avg_internal_link_ratio = _avg(records, 'internal_link_ratio')
        avg_content_pages = sum(float(item['content_pages']) for item in records) / count
        avg_ranking_velocity = _avg(records, 'ranking_velocity')
        avg_issue_density = _avg(records, 'technical_issue_density')
        avg_content_growth = _avg(records, 'content_growth_rate')
        avg_crawl_health = _avg(records, 'crawl_health_score')

        context = records[0]['cohort_context']
        rows.append(
            {
                'cohort': cohort_key,
                'industry': context['industry'],
                'site_size': context['site_size'],
                'campaign_age': context['campaign_age'],
                'content_volume': context['content_volume'],
                'geographic_market': context['geographic_market'],
                'campaign_count': count,
                'avg_internal_links': round(avg_internal_link_ratio, 6),
                'avg_internal_link_ratio': round(avg_internal_link_ratio, 6),
                'avg_content_pages': round(avg_content_pages, 6),
                'ranking_velocity': round(avg_ranking_velocity, 6),
                'avg_ranking_velocity': round(avg_ranking_velocity, 6),
                'avg_technical_issue_density': round(avg_issue_density, 6),
                'avg_content_growth_rate': round(avg_content_growth, 6),
                'avg_crawl_health_score': round(avg_crawl_health, 6),
            }
        )

    return rows


def build_cohort_profiles(db: Session, campaign_ids: list[str] | None = None) -> dict[str, dict[str, Any]]:
    aggregated_rows = aggregate_features(db, campaign_ids)
    profiles: dict[str, dict[str, Any]] = {}

    for row in aggregated_rows:
        cohort_key = str(row['cohort'])
        avg_internal_link_ratio = float(row['avg_internal_link_ratio'])
        avg_ranking_velocity = float(row['avg_ranking_velocity'])
        avg_content_growth = float(row['avg_content_growth_rate'])

        profiles[cohort_key] = {
            'cohort': cohort_key,
            'campaign_count': int(row['campaign_count']),
            'internal_link_ratio_baseline': avg_internal_link_ratio,
            'internal_link_ratio_threshold': round(max(0.1, avg_internal_link_ratio - 0.1), 6),
            'ranking_velocity_baseline': avg_ranking_velocity,
            'ranking_velocity_threshold': round(avg_ranking_velocity - 0.08, 6),
            'content_growth_baseline': avg_content_growth,
            'content_growth_threshold': round(avg_content_growth - 0.05, 6),
        }

    return profiles


def describe_campaign_cohort(db: Session, campaign_id: str) -> dict[str, str]:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        raise ValueError(f'Campaign not found: {campaign_id}')

    industry = _infer_industry(campaign.domain)
    site_size = _site_size_bucket(db, campaign_id)
    campaign_age = _campaign_age_bucket(campaign.created_at)
    content_volume = _content_volume_bucket(_published_content_count(db, campaign_id))
    geographic_market = _geographic_market(db, campaign_id)

    cohort = f'{industry}_{site_size}_{geographic_market}'.lower()
    return {
        'cohort': cohort,
        'industry': industry,
        'site_size': site_size,
        'campaign_age': campaign_age,
        'content_volume': content_volume,
        'geographic_market': geographic_market,
    }


def _campaigns_for_aggregation(db: Session, campaign_ids: list[str] | None) -> list[Campaign]:
    query = db.query(Campaign)
    if campaign_ids:
        query = query.filter(Campaign.id.in_(campaign_ids))
    return query.order_by(Campaign.created_at.asc(), Campaign.id.asc()).all()


def _latest_feature_values(db: Session, campaign_id: str) -> dict[str, float]:
    rows = (
        db.query(TemporalSignalSnapshot)
        .filter(
            TemporalSignalSnapshot.campaign_id == campaign_id,
            TemporalSignalSnapshot.metric_name.in_(_FEATURE_METRICS),
            TemporalSignalSnapshot.source == 'feature_store_v1',
        )
        .order_by(TemporalSignalSnapshot.observed_at.desc(), TemporalSignalSnapshot.id.desc())
        .all()
    )

    values: dict[str, float] = {}
    for row in rows:
        metric_name = str(row.metric_name)
        if metric_name in values:
            continue
        values[metric_name] = float(row.metric_value)

    return values


def _avg(records: list[dict[str, Any]], key: str) -> float:
    if not records:
        return 0.0
    values = [float(item['features'].get(key, 0.0) or 0.0) for item in records]
    return sum(values) / max(1, len(values))


def _infer_industry(domain: str) -> str:
    lowered = (domain or '').lower()
    if any(token in lowered for token in ('plumb', 'hvac', 'roof', 'electric', 'service')):
        return 'home_services'
    if any(token in lowered for token in ('shop', 'store', 'cart', 'ecom')):
        return 'ecommerce'
    if any(token in lowered for token in ('dental', 'legal', 'clinic', 'med')):
        return 'professional_services'
    return 'general'


def _site_size_bucket(db: Session, campaign_id: str) -> str:
    page_count = int(
        db.query(CrawlPageResult)
        .filter(CrawlPageResult.campaign_id == campaign_id)
        .count()
    )
    if page_count < 50:
        return 'small_sites'
    if page_count < 500:
        return 'mid_sites'
    return 'large_sites'


def _campaign_age_bucket(created_at: datetime) -> str:
    age_days = max(0, (datetime.now(UTC) - created_at.astimezone(UTC)).days)
    if age_days < 90:
        return 'new_campaign'
    if age_days < 365:
        return 'growing_campaign'
    return 'mature_campaign'


def _published_content_count(db: Session, campaign_id: str) -> int:
    return int(
        db.query(ContentAsset)
        .filter(ContentAsset.campaign_id == campaign_id, ContentAsset.status == 'published')
        .count()
    )


def _content_volume_bucket(content_count: int) -> str:
    if content_count < 10:
        return 'low_content'
    if content_count < 50:
        return 'mid_content'
    return 'high_content'


def _geographic_market(db: Session, campaign_id: str) -> str:
    row = (
        db.query(CampaignKeyword.location_code, func.count(CampaignKeyword.id).label('n'))
        .filter(CampaignKeyword.campaign_id == campaign_id, CampaignKeyword.location_code.isnot(None))
        .group_by(CampaignKeyword.location_code)
        .order_by(func.count(CampaignKeyword.id).desc(), CampaignKeyword.location_code.asc())
        .first()
    )
    if row is None:
        return 'unknown_market'
    return str(row[0] or 'unknown_market').lower()
