from __future__ import annotations

from collections.abc import Iterable

from app.intelligence.digital_twin.models.model_registry import get_model_parameters


class RankPredictionModel:
    def __init__(self, coefficients: dict[str, float] | None = None) -> None:
        if coefficients is not None:
            self.coefficients = dict(coefficients)
            return
        self.coefficients = dict(get_model_parameters().get('coefficients', {}))

    def predict_rank_delta(self, features: dict[str, float], actions: Iterable[dict[str, object]]) -> float:
        links_added = 0
        pages_added = 0
        issues_fixed = 0

        technical_issue_count = max(0, _as_float(features.get('technical_issue_count', 0.0)))

        for action in actions:
            action_type = str(action.get('type', '')).strip().lower()
            if action_type == 'internal_link':
                links_added += _as_non_negative_int(action.get('count', 0))
            elif action_type == 'publish_content':
                pages_added += _as_non_negative_int(action.get('pages', 0))
            elif action_type == 'fix_technical_issues':
                requested = _as_non_negative_int(action.get('count', 0))
                issues_fixed += min(requested, max(int(technical_issue_count - issues_fixed), 0))

        momentum_score = _as_float(features.get('momentum_score', 0.0))
        cohort_pattern_strength = _as_float(features.get('cohort_pattern_strength', 0.0))
        avg_rank = _as_float(features.get('avg_rank', 0.0))

        rank_delta = (
            self._coef('internal_links_added', 0.18) * links_added
            + self._coef('pages_added', 0.42) * pages_added
            + self._coef('issues_fixed', 0.26) * issues_fixed
            + self._coef('momentum_score', 0.12) * momentum_score
            + self._coef('cohort_pattern_strength', 0.08) * cohort_pattern_strength
            + self._coef('avg_rank_bias', 0.0) * avg_rank
            - self._coef('technical_issue_penalty', 0.0) * technical_issue_count
        )
        return round(rank_delta, 6)

    def _coef(self, name: str, fallback: float) -> float:
        return float(self.coefficients.get(name, fallback))


def _as_non_negative_int(value: object) -> int:
    try:
        coerced = int(value)
    except (TypeError, ValueError):
        return 0
    return max(coerced, 0)


def _as_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
