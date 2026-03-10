from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.intelligence.global_graph.graph_schema import EdgeType, NodeType
from app.intelligence.global_graph.graph_service import get_graph_store
from app.intelligence.industry_models.industry_model_registry import get_registry
from app.intelligence.strategy_evolution.strategy_experiment_engine import create_strategy_experiments
from app.intelligence.strategy_evolution.strategy_performance_analyzer import analyze_strategy_performance
from app.models.intelligence import StrategyRecommendation
from app.models.strategy_performance import StrategyPerformance


def evolve_strategy_ecosystem(db: Session, *, industry: str | None = None) -> dict[str, Any]:
    summaries = analyze_strategy_performance(db, industry=industry)
    graph_store = get_graph_store()
    industry_registry = get_registry()

    promoted = 0
    demoted = 0
    activated = 0
    for summary in summaries:
        row = db.get(StrategyPerformance, str(summary['strategy_id']))
        if row is None:
            continue
        previous_stage = str((row.metadata_json or {}).get('previous_stage', 'candidate'))
        stage = str(summary['lifecycle_stage'])
        if stage == 'promoted' and previous_stage != 'promoted':
            row.promotion_count += 1
            promoted += 1
        elif stage == 'demoted' and previous_stage != 'demoted':
            row.demotion_count += 1
            demoted += 1
        elif stage == 'active':
            activated += 1
        metadata = dict(row.metadata_json or {})
        metadata['previous_stage'] = stage
        metadata['campaign_id'] = metadata.get('campaign_id') or _latest_campaign_id(db, row.strategy_id)
        row.metadata_json = metadata
        row.notes = _stage_note(stage, float(summary['performance_score']))
        row.last_updated = datetime.now(UTC)

        strategy_node_id = _strategy_node_id(row.strategy_id)
        outcome_node_id = f'{NodeType.OUTCOME.value}:strategy_performance:{row.strategy_id.strip().lower().replace(" ", "_")}'
        graph_store.create_node(NodeType.STRATEGY, strategy_node_id, {'strategy_key': row.strategy_id, 'lifecycle_stage': stage}, session=db)
        graph_store.create_node(NodeType.OUTCOME, outcome_node_id, {'outcome_key': 'strategy_performance', 'lifecycle_stage': stage}, session=db)
        graph_store.upsert_edge(
            strategy_node_id,
            outcome_node_id,
            EdgeType.IMPROVES if stage == 'promoted' else EdgeType.CORRELATES_WITH,
            {
                'confidence': float(summary['win_rate']),
                'support_count': int(summary['sample_size']),
                'outcome_strength': float(summary['avg_delta']),
                'timestamp': datetime.now(UTC).isoformat(),
                'model_version': 'strategy_evolution_v1',
                'cohort_context': {'industry': industry} if industry else {},
            },
            session=db,
        )
        if industry:
            industry_registry.record_strategy_outcome(
                industry,
                row.strategy_id,
                success_weight=max(float(summary['avg_delta']), 0.0),
                support_weight=max(int(summary['sample_size']), 1),
                session=db,
            )

    experiments = create_strategy_experiments(db, industry=industry)
    db.flush()
    return {
        'strategies_analyzed': len(summaries),
        'promoted': promoted,
        'demoted': demoted,
        'activated': activated,
        'experiments_created': len(experiments),
        'experiments': experiments,
        'strategy_summaries': summaries,
    }


def _strategy_node_id(strategy_id: str) -> str:
    return f'{NodeType.STRATEGY.value}:{strategy_id.strip().lower().replace(" ", "_")}'


def _stage_note(stage: str, performance_score: float) -> str:
    if stage == 'promoted':
        return f'Strategy promoted with performance score {performance_score:.3f}.'
    if stage == 'demoted':
        return f'Strategy demoted with performance score {performance_score:.3f}.'
    if stage == 'active':
        return f'Strategy remains active with performance score {performance_score:.3f}.'
    return f'Strategy remains candidate with performance score {performance_score:.3f}.'


def _latest_campaign_id(db: Session, strategy_id: str) -> str | None:
    row = (
        db.query(StrategyRecommendation.campaign_id)
        .filter(StrategyRecommendation.recommendation_type == strategy_id)
        .order_by(StrategyRecommendation.created_at.desc())
        .first()
    )
    return str(row.campaign_id) if row is not None and getattr(row, 'campaign_id', None) else None
