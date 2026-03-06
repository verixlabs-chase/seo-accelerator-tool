from __future__ import annotations

from app.intelligence.industry_models.industry_model_registry import IndustryModelRegistry, get_registry


class IndustryQueryEngine:
    def __init__(self, registry: IndustryModelRegistry | None = None) -> None:
        self.registry = registry or get_registry()

    def get_industry_patterns(self, industry_id: str) -> list[tuple[str, float]]:
        model = self.registry.get_industry_model(industry_id)
        if model is None:
            return []
        return sorted(model.pattern_distribution.items(), key=lambda item: item[1], reverse=True)

    def get_industry_strategies(self, industry_id: str) -> list[tuple[str, float]]:
        model = self.registry.get_industry_model(industry_id)
        if model is None:
            return []
        return sorted(model.strategy_success_rates.items(), key=lambda item: item[1], reverse=True)

    def get_strategy_success_rate(self, industry_id: str, strategy: str) -> float:
        model = self.registry.get_industry_model(industry_id)
        if model is None:
            return 0.0
        return float(model.strategy_success_rates.get(str(strategy).strip().lower(), 0.0) or 0.0)


_QUERY_ENGINE = IndustryQueryEngine(get_registry())


def get_industry_query_engine() -> IndustryQueryEngine:
    return _QUERY_ENGINE


def get_industry_patterns(industry_id: str) -> list[tuple[str, float]]:
    return _QUERY_ENGINE.get_industry_patterns(industry_id)


def get_industry_strategies(industry_id: str) -> list[tuple[str, float]]:
    return _QUERY_ENGINE.get_industry_strategies(industry_id)


def get_strategy_success_rate(industry_id: str, strategy: str) -> float:
    return _QUERY_ENGINE.get_strategy_success_rate(industry_id, strategy)
