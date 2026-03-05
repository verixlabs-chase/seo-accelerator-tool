from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.intelligence.feature_aggregator import build_cohort_profiles, describe_campaign_cohort
from app.intelligence.feature_store import compute_features


@dataclass(frozen=True)
class PatternMatch:
    pattern_key: str
    confidence: float
    evidence: list[str]


def detect_patterns(features: dict[str, float]) -> list[PatternMatch]:
    patterns: list[PatternMatch] = []

    if (
        float(features.get('technical_issue_density', 0.0)) > 0.4
        and float(features.get('internal_link_ratio', 1.0)) < 0.6
    ):
        patterns.append(
            PatternMatch(
                pattern_key='internal_link_problem',
                confidence=0.78,
                evidence=['technical_issue_density', 'internal_link_ratio'],
            )
        )

    if (
        float(features.get('ranking_velocity', 0.0)) < -0.1
        and float(features.get('content_growth_rate', 0.0)) <= 0
    ):
        patterns.append(
            PatternMatch(
                pattern_key='declining_visibility_with_low_content_growth',
                confidence=0.72,
                evidence=['ranking_velocity', 'content_growth_rate'],
            )
        )

    return patterns


def discover_patterns_for_campaign(campaign_id: str, db: Session, *, persist_features: bool = False) -> list[dict[str, object]]:
    features = compute_features(campaign_id, db=db, persist=persist_features)
    return [
        {
            'pattern_key': match.pattern_key,
            'confidence': match.confidence,
            'evidence': match.evidence,
        }
        for match in detect_patterns(features)
    ]


def discover_cohort_patterns(
    db: Session,
    *,
    campaign_id: str,
    features: dict[str, float] | None = None,
    cohort_profiles: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, object]]:
    current_features = features or compute_features(campaign_id, db=db, persist=False)
    cohort_context = describe_campaign_cohort(db, campaign_id)
    profiles = cohort_profiles or build_cohort_profiles(db)
    profile = profiles.get(cohort_context['cohort'])
    if profile is None:
        return []

    matches: list[dict[str, object]] = []

    internal_link_ratio = float(current_features.get('internal_link_ratio', 1.0) or 1.0)
    internal_link_threshold = float(profile.get('internal_link_ratio_threshold', 0.5) or 0.5)
    if internal_link_ratio < internal_link_threshold:
        matches.append(
            {
                'pattern_key': 'internal_link_deficit',
                'confidence': 0.75,
                'evidence': ['internal_link_ratio', 'cohort_internal_link_ratio_threshold'],
                'cohort': cohort_context['cohort'],
                'reference_threshold': round(internal_link_threshold, 6),
            }
        )

    ranking_velocity = float(current_features.get('ranking_velocity', 0.0) or 0.0)
    ranking_velocity_threshold = float(profile.get('ranking_velocity_threshold', -0.1) or -0.1)
    if ranking_velocity < ranking_velocity_threshold:
        matches.append(
            {
                'pattern_key': 'cohort_ranking_velocity_lag',
                'confidence': 0.7,
                'evidence': ['ranking_velocity', 'cohort_ranking_velocity_threshold'],
                'cohort': cohort_context['cohort'],
                'reference_threshold': round(ranking_velocity_threshold, 6),
            }
        )

    content_growth_rate = float(current_features.get('content_growth_rate', 0.0) or 0.0)
    content_growth_threshold = float(profile.get('content_growth_threshold', -0.05) or -0.05)
    if content_growth_rate < content_growth_threshold:
        matches.append(
            {
                'pattern_key': 'cohort_content_growth_lag',
                'confidence': 0.68,
                'evidence': ['content_growth_rate', 'cohort_content_growth_threshold'],
                'cohort': cohort_context['cohort'],
                'reference_threshold': round(content_growth_threshold, 6),
            }
        )

    return matches
