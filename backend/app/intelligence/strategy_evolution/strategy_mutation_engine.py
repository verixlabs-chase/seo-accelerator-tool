from __future__ import annotations

from typing import Any

from app.intelligence.industry_models.industry_query_engine import get_industry_query_engine


def generate_strategy_variants(
    strategy: dict[str, Any],
    *,
    industry: str | None = None,
    variant_count: int = 3,
) -> list[dict[str, Any]]:
    strategy_id = str(strategy.get('strategy_id') or strategy.get('recommendation_type') or '')
    if not strategy_id:
        return []

    base_actions = _actions_for_strategy(strategy_id)
    industry_prior = 0.0
    if industry:
        industry_prior = float(get_industry_query_engine().get_strategy_success_rate(industry, strategy_id))

    variants: list[dict[str, Any]] = []
    for index in range(max(1, variant_count)):
        multiplier = 1.0 + ((index + 1) * 0.15)
        adjusted_actions = []
        for action in base_actions:
            item = dict(action)
            if item['type'] == 'internal_link':
                item['count'] = max(1, int(round(float(item.get('count', 1)) * multiplier)))
            elif item['type'] == 'publish_content':
                item['pages'] = max(1, int(round(float(item.get('pages', 1)) * multiplier)))
            elif item['type'] == 'fix_technical_issues':
                item['count'] = max(1, int(round(float(item.get('count', 1)) * multiplier)))
            item['industry_success_rate'] = industry_prior
            adjusted_actions.append(item)
        variants.append(
            {
                'strategy_id': strategy_id,
                'variant_strategy_id': f'{strategy_id}::variant_{index + 1}',
                'strategy_actions': adjusted_actions,
                'hypothesis': _hypothesis_for_variant(strategy_id, index + 1, multiplier, industry_prior),
                'mutation_factor': round(multiplier, 6),
                'industry_prior': round(industry_prior, 6),
            }
        )

    return variants


def _actions_for_strategy(strategy_id: str) -> list[dict[str, object]]:
    lowered = strategy_id.lower()
    if 'internal' in lowered or 'link' in lowered:
        return [{'type': 'internal_link', 'count': 4}]
    if 'content' in lowered or 'publish' in lowered:
        return [{'type': 'publish_content', 'pages': 2}]
    if 'schema' in lowered or 'title' in lowered or 'technical' in lowered:
        return [{'type': 'fix_technical_issues', 'count': 2}]
    return [{'type': 'publish_content', 'pages': 1}]


def _hypothesis_for_variant(strategy_id: str, variant_index: int, multiplier: float, industry_prior: float) -> str:
    return (
        f'Variant {variant_index} scales {strategy_id} by {multiplier:.2f}x '
        f'with industry prior {industry_prior:.2f} to test whether stronger execution volume improves expected value.'
    )
