from __future__ import annotations

from sqlalchemy.orm import Session

from app.intelligence.causal.causal_learning_engine import learn_from_experiment_completed
from app.intelligence.causal_mechanisms.mechanism_learning_engine import learn_mechanisms_from_experiment_completed


def process(db: Session, payload: dict[str, object]) -> dict[str, object]:
    edge = learn_from_experiment_completed(db, payload)
    mechanisms = learn_mechanisms_from_experiment_completed(db, payload)
    return {
        'policy_id': edge.policy_id,
        'industry': edge.industry,
        'effect_size': float(edge.effect_size),
        'confidence': float(edge.confidence),
        'sample_size': int(edge.sample_size),
        'mechanisms': mechanisms.model_dump(mode='json'),
    }
