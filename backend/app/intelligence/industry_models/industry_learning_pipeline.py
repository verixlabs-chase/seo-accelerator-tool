from __future__ import annotations

from contextlib import nullcontext
from datetime import UTC, datetime
from typing import Any

from app.intelligence.industry_models.industry_model_registry import IndustryModelRegistry, get_registry


class IndustryLearningPipeline:
    def __init__(self, registry: IndustryModelRegistry | None = None) -> None:
        self.registry = registry or get_registry()

    def update_from_pattern(self, event: dict[str, Any]) -> None:
        industry = _industry_from_event(event)
        context = self.registry.session_scope() if hasattr(self.registry, 'session_scope') else nullcontext(None)
        with context as session:
            model = self.registry.register_industry_model(industry, session=session)

            patterns = event.get('patterns') if isinstance(event.get('patterns'), list) else []
            for item in patterns:
                if not isinstance(item, dict):
                    continue
                pattern_key = str(item.get('pattern_key', '') or '').strip()
                if pattern_key:
                    self.registry.increment_pattern(industry, pattern_key, session=session)

            sample_size = int(model.sample_size) + max(len(patterns), 1)
            confidence_score = _confidence_from_sample(sample_size)
            self.registry.update_industry_model(
                industry,
                session=session,
                sample_size=sample_size,
                confidence_score=confidence_score,
                last_updated=datetime.now(UTC),
            )

    def update_from_simulation(self, event: dict[str, Any]) -> None:
        industry = _industry_from_event(event)
        context = self.registry.session_scope() if hasattr(self.registry, 'session_scope') else nullcontext(None)
        with context as session:
            model = self.registry.register_industry_model(industry, session=session)

            strategy = str(event.get('winning_strategy_id') or event.get('strategy_id') or '').strip().lower()
            predicted_rank_delta = float(event.get('predicted_rank_delta', 0.0) or 0.0)
            predicted_traffic_delta = float(event.get('predicted_traffic_delta', 0.0) or predicted_rank_delta)
            confidence = float(event.get('confidence', 0.5) or 0.5)

            simulation_weight = 0.5
            if strategy:
                success_weight = simulation_weight if predicted_rank_delta > 0 else 0.0
                self.registry.record_strategy_outcome(industry, strategy, success_weight, simulation_weight, session=session)

            next_sample = int(model.sample_size) + 1
            avg_rank_delta = _weighted_avg(model.avg_rank_delta, model.sample_size, predicted_rank_delta, simulation_weight)
            avg_traffic_delta = _weighted_avg(model.avg_traffic_delta, model.sample_size, predicted_traffic_delta, simulation_weight)
            confidence_score = max(float(model.confidence_score), min(1.0, max(confidence, _confidence_from_sample(next_sample))))

            self.registry.update_industry_model(
                industry,
                session=session,
                sample_size=next_sample,
                avg_rank_delta=round(avg_rank_delta, 6),
                avg_traffic_delta=round(avg_traffic_delta, 6),
                confidence_score=round(confidence_score, 6),
                last_updated=datetime.now(UTC),
            )

    def update_from_outcome(self, event: dict[str, Any]) -> None:
        industry = _industry_from_event(event)
        context = self.registry.session_scope() if hasattr(self.registry, 'session_scope') else nullcontext(None)
        with context as session:
            model = self.registry.register_industry_model(industry, session=session)

            strategy = str(event.get('strategy_id') or event.get('recommendation_id') or '').strip().lower()
            delta = float(event.get('delta', 0.0) or 0.0)
            traffic_delta = float(event.get('traffic_delta', delta) or delta)

            if strategy:
                success_weight = 1.0 if delta > 0 else 0.0
                self.registry.record_strategy_outcome(industry, strategy, success_weight, 1.0, session=session)

            next_sample = int(model.sample_size) + 1
            avg_rank_delta = _weighted_avg(model.avg_rank_delta, model.sample_size, delta, 1.0)
            avg_traffic_delta = _weighted_avg(model.avg_traffic_delta, model.sample_size, traffic_delta, 1.0)
            confidence_score = _confidence_from_sample(next_sample)

            self.registry.update_industry_model(
                industry,
                session=session,
                sample_size=next_sample,
                avg_rank_delta=round(avg_rank_delta, 6),
                avg_traffic_delta=round(avg_traffic_delta, 6),
                confidence_score=round(confidence_score, 6),
                last_updated=datetime.now(UTC),
            )


def get_industry_learning_pipeline() -> IndustryLearningPipeline:
    return IndustryLearningPipeline(get_registry())


def _industry_from_event(event: dict[str, Any]) -> str:
    return str(event.get('industry') or event.get('industry_id') or 'unknown').strip().lower().replace(' ', '_') or 'unknown'


def _confidence_from_sample(sample_size: int) -> float:
    return min(1.0, max(0.05, float(sample_size) / 100.0))


def _weighted_avg(current_avg: float, current_weight: int, value: float, weight: float) -> float:
    total_weight = max(float(current_weight), 0.0) + max(float(weight), 0.0)
    if total_weight <= 0.0:
        return 0.0
    return ((float(current_avg) * max(float(current_weight), 0.0)) + (float(value) * max(float(weight), 0.0))) / total_weight
