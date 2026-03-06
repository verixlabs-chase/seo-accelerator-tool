from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy.orm import Session

from app.intelligence.digital_twin.models.confidence_estimator import ConfidenceEstimator
from app.intelligence.digital_twin.models.model_registry import get_model_parameters
from app.intelligence.digital_twin.models.rank_prediction_model import RankPredictionModel
from app.intelligence.digital_twin.models.traffic_prediction_model import TrafficPredictionModel
from app.intelligence.digital_twin.twin_state_model import DigitalTwinState
from app.models.digital_twin_simulation import DigitalTwinSimulation


def simulate_strategy(
    twin_state: DigitalTwinState,
    strategy_actions: Iterable[dict[str, object]],
    *,
    db: Session | None = None,
    strategy_id: str | None = None,
) -> dict[str, float | str | None]:
    actions = list(strategy_actions)
    features = _build_feature_payload(twin_state, actions)

    rank_model = RankPredictionModel()
    traffic_model = TrafficPredictionModel()
    confidence_estimator = ConfidenceEstimator()

    predicted_rank_delta = rank_model.predict_rank_delta(features, actions)
    predicted_traffic_delta = traffic_model.predict_traffic_delta(predicted_rank_delta, twin_state.traffic_estimate)

    registry = get_model_parameters()
    confidence_defaults = dict(registry.get('confidence_parameters', {}))
    confidence = confidence_estimator.compute_confidence(
        pattern_support_count=_sum_int_field(actions, 'pattern_support_count') or _sample_size(actions),
        historical_outcome_variance=float(confidence_defaults.get('historical_variance_baseline', 0.25)),
        cohort_confidence=float(features.get('cohort_pattern_strength', 0.0)),
        sample_size=_sample_size(actions),
    )

    expected_value = round(float(predicted_rank_delta) * float(confidence), 6)
    model_version = _model_version(registry)

    simulation_id: str | None = None
    if db is not None:
        row = DigitalTwinSimulation(
            campaign_id=twin_state.campaign_id,
            strategy_actions=actions,
            predicted_rank_delta=float(predicted_rank_delta),
            predicted_traffic_delta=float(predicted_traffic_delta),
            confidence=float(confidence),
            expected_value=float(expected_value),
            selected_strategy=False,
            model_version=model_version,
        )
        db.add(row)
        db.flush()
        simulation_id = row.id

    return {
        'strategy_id': strategy_id,
        'simulation_id': simulation_id,
        'predicted_rank_delta': round(float(predicted_rank_delta), 6),
        'predicted_traffic_delta': round(float(predicted_traffic_delta), 6),
        'confidence': round(float(confidence), 6),
        'expected_value': expected_value,
        'model_version': model_version,
    }


def _model_version(registry: dict[str, object]) -> str:
    rank_version = str(registry.get('rank_model_version', 'v1'))
    traffic_version = str(registry.get('traffic_model_version', 'v1'))
    confidence_version = str(registry.get('confidence_model_version', 'v1'))
    return f'rank={rank_version};traffic={traffic_version};confidence={confidence_version}'


def _build_feature_payload(
    twin_state: DigitalTwinState,
    actions: list[dict[str, object]],
) -> dict[str, float]:
    cohort_pattern_strength = _average_float_field(actions, 'cohort_pattern_strength')
    if cohort_pattern_strength == 0.0:
        cohort_pattern_strength = _average_float_field(actions, 'cohort_confidence')

    industry_success_rate = _average_float_field(actions, 'industry_success_rate')
    if industry_success_rate > 0.0:
        cohort_pattern_strength = max(cohort_pattern_strength, industry_success_rate)

    predicted_confidence = _average_float_field(actions, 'predicted_confidence')
    if predicted_confidence > 0.0:
        cohort_pattern_strength = max(cohort_pattern_strength, predicted_confidence)

    predicted_rank_delta = _average_float_field(actions, 'predicted_rank_delta')

    return {
        'internal_link_count': float(twin_state.internal_link_count),
        'content_page_count': float(twin_state.content_page_count),
        'technical_issue_count': float(twin_state.technical_issue_count),
        'avg_rank': float(twin_state.avg_rank),
        'momentum_score': float(twin_state.momentum_score),
        'cohort_pattern_strength': float(cohort_pattern_strength),
        'predicted_rank_delta_prior': float(predicted_rank_delta),
    }


def _sample_size(actions: list[dict[str, object]]) -> int:
    if not actions:
        return 0

    total = 0
    for action in actions:
        action_type = str(action.get('type', '')).strip().lower()
        if action_type == 'internal_link':
            total += _as_non_negative_int(action.get('count', 0))
        elif action_type == 'publish_content':
            total += _as_non_negative_int(action.get('pages', 0))
        elif action_type == 'fix_technical_issues':
            total += _as_non_negative_int(action.get('count', 0))

    return max(total, len(actions))


def _sum_int_field(actions: list[dict[str, object]], key: str) -> int:
    total = 0
    for action in actions:
        total += _as_non_negative_int(action.get(key, 0))
    return total


def _average_float_field(actions: list[dict[str, object]], key: str) -> float:
    values: list[float] = []
    for action in actions:
        raw = action.get(key)
        if raw is None:
            continue
        try:
            values.append(float(raw))
        except (TypeError, ValueError):
            continue

    if not values:
        return 0.0
    return max(0.0, min(1.0, sum(values) / len(values)))


def _as_non_negative_int(value: object) -> int:
    try:
        coerced = int(value)
    except (TypeError, ValueError):
        return 0
    return max(coerced, 0)
