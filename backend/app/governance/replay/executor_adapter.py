from __future__ import annotations

from typing import Any

from app.governance.replay.schema import ReplayCase
from app.services.strategy_engine.engine import build_campaign_strategy
from app.services.strategy_engine.schemas import StrategyWindow


def execute_case(case: ReplayCase) -> dict[str, Any]:
    payload = build_campaign_strategy(
        campaign_id=case.campaign_id,
        window=StrategyWindow.model_validate(case.input_payload['window']),
        raw_signals=case.input_payload.get('raw_signals', {}),
        tier=str(case.input_payload.get('tier', 'pro')),
    )
    return payload.model_dump(mode='json')
