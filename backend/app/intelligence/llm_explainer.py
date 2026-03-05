from __future__ import annotations


def explain_recommendation(recommendation: dict, signals: dict, patterns: list[dict]) -> str:
    recommendation_type = str(recommendation.get('recommendation_type', 'unknown'))
    pattern_keys = ', '.join(str(item.get('pattern_key', 'unknown')) for item in patterns) or 'none'
    signal_count = len(signals)
    return (
        'Explanation module placeholder. '
        f'Deterministic recommendation type: {recommendation_type}. '
        f'Patterns referenced: {pattern_keys}. '
        f'Signal fields considered: {signal_count}.'
    )
