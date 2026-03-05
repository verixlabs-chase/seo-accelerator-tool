from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

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
