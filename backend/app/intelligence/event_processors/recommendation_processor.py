from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.events.event_bus import publish_event
from app.events.event_types import EventType
from app.intelligence.feature_store import compute_features
from app.intelligence.policy_engine import derive_policy, generate_recommendations, score_policy


def process(payload: dict[str, object]) -> dict[str, object] | None:
    campaign_id = str(payload.get('campaign_id', '') or '')
    if not campaign_id:
        return None

    db = payload.get('db')
    patterns = payload.get('patterns')
    pattern_rows = patterns if isinstance(patterns, list) else []

    if isinstance(db, Session):
        features = payload.get('features') if isinstance(payload.get('features'), dict) else compute_features(campaign_id, db=db, persist=False)
        recommendations_payload = _build_recommendations(pattern_rows, features)
        publish_event(
            EventType.RECOMMENDATION_GENERATED.value,
            {'campaign_id': campaign_id, **recommendations_payload},
        )
        return {'campaign_id': campaign_id, **recommendations_payload}

    session = SessionLocal()
    try:
        features = payload.get('features') if isinstance(payload.get('features'), dict) else compute_features(campaign_id, db=session, persist=False)
        recommendations_payload = _build_recommendations(pattern_rows, features)
        publish_event(
            EventType.RECOMMENDATION_GENERATED.value,
            {'campaign_id': campaign_id, **recommendations_payload},
        )
        return {'campaign_id': campaign_id, **recommendations_payload}
    finally:
        session.close()


def _build_recommendations(pattern_rows: list[object], features: dict[str, object]) -> dict[str, object]:
    policies = [score_policy(policy, features) for policy in derive_policy(pattern_rows)]
    recommendation_rows = [recommendation for policy in policies for recommendation in generate_recommendations(policy)]

    candidate_strategies = []
    for idx, row in enumerate(recommendation_rows):
        actions = row.get('recommended_actions', []) if isinstance(row, dict) else []
        candidate_strategies.append(
            {
                'strategy_id': str(row.get('recommendation_id', f'generated_{idx}')),
                'strategy_actions': _actions_to_strategy(actions),
                'recommendation_id': row.get('recommendation_id'),
            }
        )

    return {
        'features': features,
        'policies': policies,
        'recommendations': recommendation_rows,
        'candidate_strategies': candidate_strategies,
    }


def _actions_to_strategy(actions: list[object]) -> list[dict[str, object]]:
    strategy_actions: list[dict[str, object]] = []
    for action in actions:
        normalized = str(action).lower()
        if 'link' in normalized:
            strategy_actions.append({'type': 'internal_link', 'count': 1})
        elif 'content' in normalized or 'publish' in normalized:
            strategy_actions.append({'type': 'publish_content', 'pages': 1})
        elif 'title' in normalized or 'schema' in normalized or 'fix' in normalized:
            strategy_actions.append({'type': 'fix_technical_issues', 'count': 1})
    if not strategy_actions:
        strategy_actions.append({'type': 'publish_content', 'pages': 1})
    return strategy_actions
