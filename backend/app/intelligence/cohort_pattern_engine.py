from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.intelligence.cohort_feature_aggregator import aggregate_feature_profiles, build_cohort_rows
from app.models.strategy_cohort_pattern import StrategyCohortPattern

MINIMUM_SAMPLES = 3
CONFIDENCE_THRESHOLD = 0.6


def discover_cohort_patterns(
    db: Session,
    *,
    minimum_samples: int = MINIMUM_SAMPLES,
    confidence_threshold: float = CONFIDENCE_THRESHOLD,
    persist: bool = True,
) -> list[StrategyCohortPattern]:
    rows = build_cohort_rows(db)
    profiles = aggregate_feature_profiles(rows)

    accepted: list[StrategyCohortPattern] = []
    for profile in profiles:
        candidates = _profile_candidates(profile)
        for candidate in candidates:
            support_count = int(candidate['support_count'])
            confidence = float(candidate['confidence'])
            if support_count < minimum_samples or confidence < confidence_threshold:
                continue

            row = StrategyCohortPattern(
                pattern_name=str(candidate['pattern_name']),
                feature_name=str(candidate['feature_name']),
                cohort_definition=str(candidate['cohort_definition']),
                pattern_strength=float(candidate['pattern_strength']),
                support_count=support_count,
                confidence=confidence,
                created_at=datetime.now(UTC),
            )
            accepted.append(row)
            if persist:
                db.add(row)

    if persist and accepted:
        db.commit()

    return accepted


def _profile_candidates(profile: dict[str, Any]) -> list[dict[str, Any]]:
    cohort = str(profile['cohort_definition'])
    support_count = int(profile['support_count'])
    avg_internal_link_ratio = float(profile['avg_internal_link_ratio'])
    avg_content_velocity = float(profile['avg_content_velocity'])
    avg_traffic_growth = float(profile['avg_traffic_growth'])
    avg_technical_issue_density = float(profile['avg_technical_issue_density'])
    avg_ranking_velocity = float(profile['avg_ranking_velocity'])
    avg_outcome_delta = float(profile['avg_outcome_delta'])

    candidates: list[dict[str, Any]] = []

    if avg_internal_link_ratio < 0.55 and avg_outcome_delta > 0:
        strength = min(1.0, ((0.55 - avg_internal_link_ratio) / 0.55) + min(avg_outcome_delta, 1.0) * 0.4)
        confidence = _confidence_from_support(support_count, signal_gap=max(0.0, 0.55 - avg_internal_link_ratio))
        candidates.append(
            {
                'pattern_name': 'low_internal_links_ranking_growth_after_linking',
                'feature_name': 'internal_link_ratio',
                'cohort_definition': cohort,
                'pattern_strength': round(strength, 6),
                'support_count': support_count,
                'confidence': round(confidence, 6),
            }
        )

    if avg_content_velocity > 0.05 and avg_traffic_growth > 0.03:
        strength = min(1.0, avg_content_velocity + avg_traffic_growth)
        confidence = _confidence_from_support(support_count, signal_gap=min(1.0, avg_content_velocity))
        candidates.append(
            {
                'pattern_name': 'high_content_velocity_traffic_growth',
                'feature_name': 'content_velocity',
                'cohort_definition': cohort,
                'pattern_strength': round(strength, 6),
                'support_count': support_count,
                'confidence': round(confidence, 6),
            }
        )

    if avg_technical_issue_density < 0.2 and avg_ranking_velocity > 0:
        strength = min(1.0, (0.2 - avg_technical_issue_density) + avg_ranking_velocity)
        confidence = _confidence_from_support(support_count, signal_gap=max(0.0, 0.2 - avg_technical_issue_density))
        candidates.append(
            {
                'pattern_name': 'low_technical_issues_faster_ranking_improvements',
                'feature_name': 'technical_issue_density',
                'cohort_definition': cohort,
                'pattern_strength': round(strength, 6),
                'support_count': support_count,
                'confidence': round(confidence, 6),
            }
        )

    return candidates


def _confidence_from_support(support_count: int, *, signal_gap: float) -> float:
    support_component = min(1.0, max(0.0, support_count / 10.0))
    signal_component = min(1.0, max(0.0, signal_gap))
    return min(1.0, 0.45 + 0.4 * support_component + 0.15 * signal_component)
