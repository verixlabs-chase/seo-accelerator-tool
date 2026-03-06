from __future__ import annotations

from app.intelligence.industry_models.industry_learning_pipeline import IndustryLearningPipeline
from app.intelligence.industry_models.industry_model_registry import IndustryModelRegistry
from app.intelligence.industry_models.industry_query_engine import IndustryQueryEngine


def test_industry_models_created_and_listed() -> None:
    registry = IndustryModelRegistry()
    model = registry.register_industry_model('roofing')

    assert model.industry_id == 'roofing'
    assert registry.get_industry_model('roofing') is not None
    assert 'roofing' in registry.list_industries()


def test_learning_pipeline_updates_stats_from_events() -> None:
    registry = IndustryModelRegistry()
    pipeline = IndustryLearningPipeline(registry)

    pipeline.update_from_pattern(
        {
            'industry': 'roofing',
            'patterns': [
                {'pattern_key': 'service_area_page_cluster', 'confidence': 0.8},
                {'pattern_key': 'service_area_page_cluster', 'confidence': 0.7},
                {'pattern_key': 'local_authority_deficit', 'confidence': 0.6},
            ],
        }
    )
    pipeline.update_from_simulation(
        {
            'industry': 'roofing',
            'winning_strategy_id': 'strategy:service_area_pages',
            'predicted_rank_delta': 1.8,
            'predicted_traffic_delta': 12.0,
            'confidence': 0.72,
        }
    )
    pipeline.update_from_outcome(
        {
            'industry': 'roofing',
            'strategy_id': 'strategy:service_area_pages',
            'delta': 2.1,
            'traffic_delta': 16.0,
        }
    )

    model = registry.get_industry_model('roofing')
    assert model is not None
    assert model.sample_size >= 3
    assert model.avg_rank_delta > 0
    assert model.avg_traffic_delta > 0
    assert model.confidence_score > 0
    assert 'service_area_page_cluster' in model.pattern_distribution
    assert 'strategy:service_area_pages' in model.strategy_success_rates


def test_query_engine_returns_strategies_and_patterns() -> None:
    registry = IndustryModelRegistry()
    pipeline = IndustryLearningPipeline(registry)
    query = IndustryQueryEngine(registry)

    for _ in range(3):
        pipeline.update_from_pattern({'industry': 'plumbing', 'patterns': [{'pattern_key': 'local_authority_deficit'}]})
    pipeline.update_from_outcome({'industry': 'plumbing', 'strategy_id': 'strategy:gbp_optimization', 'delta': 1.2})
    pipeline.update_from_outcome({'industry': 'plumbing', 'strategy_id': 'strategy:gbp_optimization', 'delta': -0.2})

    patterns = query.get_industry_patterns('plumbing')
    strategies = query.get_industry_strategies('plumbing')

    assert patterns
    assert patterns[0][0] == 'local_authority_deficit'
    assert strategies
    assert strategies[0][0] == 'strategy:gbp_optimization'
    assert 0.0 <= query.get_strategy_success_rate('plumbing', 'strategy:gbp_optimization') <= 1.0


def test_industries_remain_isolated() -> None:
    registry = IndustryModelRegistry()
    pipeline = IndustryLearningPipeline(registry)
    query = IndustryQueryEngine(registry)

    pipeline.update_from_outcome({'industry': 'roofing', 'strategy_id': 'strategy:service_area_pages', 'delta': 2.3})
    pipeline.update_from_outcome({'industry': 'restaurants', 'strategy_id': 'strategy:menu_schema', 'delta': 1.1})

    roofing_strategies = {name for name, _rate in query.get_industry_strategies('roofing')}
    restaurant_strategies = {name for name, _rate in query.get_industry_strategies('restaurants')}

    assert 'strategy:service_area_pages' in roofing_strategies
    assert 'strategy:menu_schema' not in roofing_strategies
    assert 'strategy:menu_schema' in restaurant_strategies
    assert 'strategy:service_area_pages' not in restaurant_strategies
