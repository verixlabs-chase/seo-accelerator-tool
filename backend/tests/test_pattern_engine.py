from __future__ import annotations

from app.intelligence.pattern_engine import detect_patterns


def test_detect_patterns_finds_internal_link_problem() -> None:
    features = {
        'technical_issue_density': 0.6,
        'internal_link_ratio': 0.4,
        'ranking_velocity': 0.0,
        'content_growth_rate': 0.0,
    }

    matches = detect_patterns(features)
    keys = [item.pattern_key for item in matches]

    assert 'internal_link_problem' in keys


def test_detect_patterns_finds_declining_visibility_pattern() -> None:
    features = {
        'technical_issue_density': 0.1,
        'internal_link_ratio': 0.9,
        'ranking_velocity': -0.3,
        'content_growth_rate': -0.1,
    }

    matches = detect_patterns(features)
    keys = [item.pattern_key for item in matches]

    assert 'declining_visibility_with_low_content_growth' in keys
