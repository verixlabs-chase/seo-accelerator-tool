from __future__ import annotations

from app.db.session import SessionLocal
from app.governance.replay.schema import ReplayCase
from app.services.strategy_build_service import build_campaign_strategy_idempotent
from app.services.strategy_engine.schemas import StrategyWindow


def execute_case(case: ReplayCase) -> dict:
    db = SessionLocal()
    try:
        payload = build_campaign_strategy_idempotent(
            db,
            tenant_id=case.tenant_id,
            campaign_id=case.campaign_id,
            window=StrategyWindow.model_validate(case.input_payload["window"]),
            raw_signals=case.input_payload.get("raw_signals", {}),
            tier=str(case.input_payload.get("tier", "pro")),
        )
        return payload.model_dump(mode="json")
    finally:
        db.close()
