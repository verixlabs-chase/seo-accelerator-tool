from __future__ import annotations

from typing import Any, Callable

from sqlalchemy.orm import Session

from app.intelligence.digital_twin.strategy_simulation_engine import simulate_strategy
from app.intelligence.digital_twin.twin_state_model import DigitalTwinState
from app.intelligence.strategy_evolution.strategy_mutation_engine import generate_strategy_variants
from app.models.strategy_experiment import StrategyExperiment
from app.models.strategy_performance import StrategyPerformance


def create_strategy_experiments(
    db: Session,
    *,
    industry: str | None = None,
    top_k: int = 5,
    twin_state_builder: Callable[[Session, str], Any] | None = None,
    simulate_fn: Callable[..., dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    builder = twin_state_builder or DigitalTwinState.from_campaign_data
    simulator = simulate_fn or simulate_strategy

    rows = (
        db.query(StrategyPerformance)
        .filter(StrategyPerformance.lifecycle_stage.in_(['promoted', 'active']))
        .order_by(StrategyPerformance.performance_score.desc(), StrategyPerformance.sample_size.desc())
        .limit(max(1, top_k))
        .all()
    )

    experiments: list[dict[str, Any]] = []
    for row in rows:
        campaign_id = str((row.metadata_json or {}).get('campaign_id') or '')
        if not campaign_id:
            continue
        twin_state = builder(db, campaign_id)
        for variant in generate_strategy_variants({'strategy_id': row.strategy_id}, industry=industry):
            simulation = simulator(
                twin_state,
                variant['strategy_actions'],
                db=None,
                strategy_id=variant['variant_strategy_id'],
            )
            experiment = StrategyExperiment(
                strategy_id=row.strategy_id,
                variant_strategy_id=variant['variant_strategy_id'],
                campaign_id=campaign_id,
                hypothesis=str(variant['hypothesis']),
                mutation_payload=list(variant['strategy_actions']),
                predicted_rank_delta=float(simulation.get('predicted_rank_delta', 0.0) or 0.0),
                predicted_traffic_delta=float(simulation.get('predicted_traffic_delta', 0.0) or 0.0),
                confidence=float(simulation.get('confidence', 0.0) or 0.0),
                expected_value=float(simulation.get('expected_value', 0.0) or 0.0),
                status='proposed',
                metadata_json={
                    'industry': industry,
                    'mutation_factor': variant.get('mutation_factor'),
                    'industry_prior': variant.get('industry_prior'),
                },
            )
            db.add(experiment)
            db.flush()
            experiments.append(
                {
                    'experiment_id': experiment.id,
                    'strategy_id': row.strategy_id,
                    'variant_strategy_id': experiment.variant_strategy_id,
                    'campaign_id': campaign_id,
                    'expected_value': round(experiment.expected_value, 6),
                    'confidence': round(experiment.confidence, 6),
                }
            )

    db.flush()
    return experiments
