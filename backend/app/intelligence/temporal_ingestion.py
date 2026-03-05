from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.campaign import Campaign
from app.models.temporal import TemporalSignalSnapshot, TemporalSignalType

_SIGNAL_TYPE_BY_METRIC: dict[str, TemporalSignalType] = {
    'avg_rank': TemporalSignalType.RANK,
    'avg_position': TemporalSignalType.RANK,
    'position_delta': TemporalSignalType.RANK,
    'ranking_velocity': TemporalSignalType.RANK,
    'review_velocity': TemporalSignalType.REVIEW,
    'review_count': TemporalSignalType.REVIEW,
    'avg_rating': TemporalSignalType.REVIEW,
    'local_health': TemporalSignalType.REVIEW,
    'content_count': TemporalSignalType.CONTENT,
    'clicks': TemporalSignalType.TRAFFIC,
    'impressions': TemporalSignalType.TRAFFIC,
    'ctr': TemporalSignalType.TRAFFIC,
    'sessions': TemporalSignalType.TRAFFIC,
    'conversions': TemporalSignalType.CONVERSION,
}


def write_temporal_signals(
    campaign_id: str,
    signals: dict[str, Any],
    *,
    db: Session | None = None,
    observed_at: datetime | None = None,
    source: str = 'signal_assembler_v1',
    tenant_id: str | None = None,
) -> dict[str, int]:
    owns_session = db is None
    session = db or SessionLocal()
    observed = observed_at or datetime.now(UTC)

    try:
        campaign = session.get(Campaign, campaign_id)
        if campaign is None:
            raise ValueError(f'Campaign not found: {campaign_id}')

        _ = tenant_id or campaign.tenant_id
        inserted = 0
        skipped = 0

        for metric_name, raw_value in signals.items():
            numeric = _coerce_numeric(raw_value)
            if numeric is None:
                skipped += 1
                continue

            signal_type = _SIGNAL_TYPE_BY_METRIC.get(metric_name, TemporalSignalType.CUSTOM)
            confidence = _confidence_for_metric(metric_name)
            version_hash = _version_hash(
                campaign_id=campaign_id,
                metric_name=metric_name,
                metric_value=numeric,
                observed_at=observed,
                source=source,
            )

            existing = (
                session.query(TemporalSignalSnapshot)
                .filter(
                    TemporalSignalSnapshot.campaign_id == campaign_id,
                    TemporalSignalSnapshot.signal_type == signal_type,
                    TemporalSignalSnapshot.metric_name == metric_name,
                    TemporalSignalSnapshot.observed_at == observed,
                    TemporalSignalSnapshot.source == source,
                    TemporalSignalSnapshot.version_hash == version_hash,
                )
                .first()
            )
            if existing is not None:
                skipped += 1
                continue

            row = TemporalSignalSnapshot(
                campaign_id=campaign_id,
                signal_type=signal_type,
                metric_name=metric_name,
                metric_value=numeric,
                observed_at=observed,
                source=source,
                confidence=confidence,
                version_hash=version_hash,
            )
            session.add(row)
            inserted += 1

        if inserted > 0:
            session.flush()
            if owns_session:
                session.commit()

        return {'inserted': inserted, 'skipped': skipped}
    finally:
        if owns_session:
            session.close()


def _coerce_numeric(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _confidence_for_metric(metric_name: str) -> float:
    if metric_name in {'clicks', 'impressions', 'sessions', 'conversions'}:
        return 0.97
    if metric_name in {'avg_rank', 'avg_position', 'position_delta', 'ranking_velocity'}:
        return 0.92
    if metric_name in {'technical_issue_count', 'crawl_errors'}:
        return 0.95
    if metric_name in {'local_health', 'review_velocity', 'avg_rating'}:
        return 0.88
    return 0.8


def _version_hash(*, campaign_id: str, metric_name: str, metric_value: float, observed_at: datetime, source: str) -> str:
    material = f'{campaign_id}|{metric_name}|{metric_value:.10f}|{observed_at.isoformat()}|{source}'
    return sha256(material.encode('utf-8')).hexdigest()
