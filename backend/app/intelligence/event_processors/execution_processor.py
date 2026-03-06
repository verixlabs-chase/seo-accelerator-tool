from __future__ import annotations

import json

from app.db.session import SessionLocal
from app.events.event_bus import publish_event
from app.events.event_types import EventType
from app.intelligence.recommendation_execution_engine import execute_recommendation, schedule_execution


def process(payload: dict[str, object]) -> dict[str, object] | None:
    recommendation_id = str(payload.get('recommendation_id', '') or '')
    campaign_id = str(payload.get('campaign_id', '') or '')
    if not recommendation_id:
        return None

    session = SessionLocal()
    try:
        execution = schedule_execution(recommendation_id, db=session)
        if execution is None or isinstance(execution, dict):
            session.commit()
            return None

        scheduled = {
            'campaign_id': campaign_id or execution.campaign_id,
            'recommendation_id': recommendation_id,
            'execution_id': execution.id,
            'status': execution.status,
        }
        publish_event(EventType.EXECUTION_SCHEDULED.value, scheduled)

        started = {
            'campaign_id': campaign_id or execution.campaign_id,
            'recommendation_id': recommendation_id,
            'execution_id': execution.id,
            'status': 'running',
        }
        publish_event(EventType.EXECUTION_STARTED.value, started)

        completed_execution = execute_recommendation(execution.id, db=session, dry_run=False)
        session.commit()
        if completed_execution is None or isinstance(completed_execution, dict):
            return scheduled

        result_summary = {}
        if completed_execution.result_summary:
            try:
                parsed = json.loads(completed_execution.result_summary)
                if isinstance(parsed, dict):
                    result_summary = parsed
            except (json.JSONDecodeError, TypeError):
                result_summary = {}

        completed = {
            'campaign_id': campaign_id or completed_execution.campaign_id,
            'recommendation_id': recommendation_id,
            'execution_id': completed_execution.id,
            'status': completed_execution.status,
            'result': result_summary,
        }
        publish_event(EventType.EXECUTION_COMPLETED.value, completed)
        return completed
    finally:
        session.close()
