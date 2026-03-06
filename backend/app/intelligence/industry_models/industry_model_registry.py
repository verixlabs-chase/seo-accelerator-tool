from __future__ import annotations

from datetime import UTC, datetime

from app.intelligence.industry_models.industry_schema import IndustryModel


class IndustryModelRegistry:
    def __init__(self) -> None:
        self._models: dict[str, IndustryModel] = {}
        self._pattern_counts: dict[str, dict[str, int]] = {}
        self._strategy_successes: dict[str, dict[str, float]] = {}
        self._strategy_support: dict[str, dict[str, float]] = {}

    def register_industry_model(self, industry_id: str, industry_name: str | None = None) -> IndustryModel:
        key = _normalize_industry(industry_id)
        existing = self._models.get(key)
        if existing is not None:
            return existing

        model = IndustryModel(
            industry_id=key,
            industry_name=industry_name or key,
            pattern_distribution={},
            strategy_success_rates={},
            avg_rank_delta=0.0,
            avg_traffic_delta=0.0,
            confidence_score=0.0,
            sample_size=0,
        )
        self._models[key] = model
        self._pattern_counts.setdefault(key, {})
        self._strategy_successes.setdefault(key, {})
        self._strategy_support.setdefault(key, {})
        return model

    def get_industry_model(self, industry_id: str) -> IndustryModel | None:
        return self._models.get(_normalize_industry(industry_id))

    def update_industry_model(self, industry_id: str, **updates: object) -> IndustryModel:
        model = self.register_industry_model(industry_id)
        for field_name, value in updates.items():
            if hasattr(model, field_name):
                setattr(model, field_name, value)
        model.last_updated = datetime.now(UTC).isoformat()
        return model

    def list_industries(self) -> list[str]:
        return sorted(self._models.keys())

    def increment_pattern(self, industry_id: str, pattern_key: str) -> IndustryModel:
        model = self.register_industry_model(industry_id)
        counts = self._pattern_counts.setdefault(model.industry_id, {})
        key = str(pattern_key).strip().lower()
        counts[key] = counts.get(key, 0) + 1
        total = sum(counts.values())
        model.pattern_distribution = {
            item: round(count / max(total, 1), 6)
            for item, count in sorted(counts.items())
        }
        model.last_updated = datetime.now(UTC).isoformat()
        return model

    def record_strategy_outcome(self, industry_id: str, strategy: str, success_weight: float, support_weight: float) -> IndustryModel:
        model = self.register_industry_model(industry_id)
        strategy_key = str(strategy).strip().lower()
        successes = self._strategy_successes.setdefault(model.industry_id, {})
        support = self._strategy_support.setdefault(model.industry_id, {})

        successes[strategy_key] = float(successes.get(strategy_key, 0.0)) + float(success_weight)
        support[strategy_key] = float(support.get(strategy_key, 0.0)) + float(support_weight)

        model.strategy_success_rates = {
            key: round(float(successes.get(key, 0.0)) / max(float(support.get(key, 0.0)), 1.0), 6)
            for key in sorted(support.keys())
        }
        model.last_updated = datetime.now(UTC).isoformat()
        return model


_REGISTRY = IndustryModelRegistry()


def register_industry_model(industry_id: str, industry_name: str | None = None) -> IndustryModel:
    return _REGISTRY.register_industry_model(industry_id, industry_name)


def get_industry_model(industry_id: str) -> IndustryModel | None:
    return _REGISTRY.get_industry_model(industry_id)


def update_industry_model(industry_id: str, **updates: object) -> IndustryModel:
    return _REGISTRY.update_industry_model(industry_id, **updates)


def list_industries() -> list[str]:
    return _REGISTRY.list_industries()


def get_registry() -> IndustryModelRegistry:
    return _REGISTRY


def _normalize_industry(industry_id: str) -> str:
    normalized = str(industry_id or '').strip().lower().replace(' ', '_')
    return normalized or 'unknown'
