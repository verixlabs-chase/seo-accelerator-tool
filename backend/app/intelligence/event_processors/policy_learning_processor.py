from __future__ import annotations

from app.db.session import SessionLocal
from app.events.event_bus import publish_event
from app.events.event_types import EventType
from app.intelligence.digital_twin.models.training_pipeline import train_prediction_models
from app.intelligence.network_learning.global_intelligence_network import run_global_intelligence_network
from app.intelligence.policy_update_engine import evolve_strategy_ecosystem, update_policy_priority_weights, update_policy_weights


def process(payload: dict[str, object]) -> dict[str, object]:
    _ = payload
    session = SessionLocal()
    try:
        recommendation_updates = update_policy_weights(session)
        policy_updates = update_policy_priority_weights(session)
        training = train_prediction_models(session)
        evolution = evolve_strategy_ecosystem(session)
        network_learning = run_global_intelligence_network(session)
        session.commit()
        result = {
            'recommendation_weight_updates': recommendation_updates,
            'policy_weight_updates': policy_updates,
            'model_training': {
                'trained': bool(training.get('trained')),
                'rank_model_version': training.get('model_registry', {}).get('rank_model_version'),
            },
            'strategy_evolution': evolution,
            'network_learning': network_learning,
        }
        publish_event(EventType.POLICY_UPDATED.value, result)
        return result
    finally:
        session.close()
