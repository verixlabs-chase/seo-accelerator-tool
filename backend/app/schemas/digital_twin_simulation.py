from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class DigitalTwinSimulationOut(BaseModel):
    id: str
    campaign_id: str
    strategy_actions: list[dict[str, object]]
    predicted_rank_delta: float
    predicted_traffic_delta: float
    confidence: float
    expected_value: float
    selected_strategy: bool
    model_version: str
    actual_rank_delta: float | None = None
    actual_traffic_delta: float | None = None
    prediction_error_rank: float | None = None
    prediction_error_traffic: float | None = None
    created_at: datetime

    model_config = {'from_attributes': True}
