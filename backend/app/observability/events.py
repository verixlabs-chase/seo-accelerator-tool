from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger('lsos.observability')


def _emit(event_name: str, payload: dict[str, Any]) -> None:
    message = {
        'event': event_name,
        **payload,
    }
    logger.info(json.dumps(message, sort_keys=True, separators=(',', ':')))


def emit_automation_event(*, campaign_id: str, evaluation_date: str, status: str, decision_hash: str | None) -> None:
    _emit(
        'automation_event',
        {
            'campaign_id': campaign_id,
            'evaluation_date': evaluation_date,
            'status': status,
            'decision_hash': decision_hash,
        },
    )


def emit_phase_transition(*, campaign_id: str, prior_phase: str, new_phase: str, decision_hash: str | None) -> None:
    _emit(
        'phase_transition',
        {
            'campaign_id': campaign_id,
            'prior_phase': prior_phase,
            'new_phase': new_phase,
            'decision_hash': decision_hash,
        },
    )


def emit_rule_trigger(*, campaign_id: str, triggered_rules: list[str], decision_hash: str | None) -> None:
    _emit(
        'rule_trigger',
        {
            'campaign_id': campaign_id,
            'triggered_rules': sorted(triggered_rules),
            'decision_hash': decision_hash,
        },
    )