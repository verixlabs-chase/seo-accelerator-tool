from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class VersionTuple(BaseModel):
    model_config = ConfigDict(extra="forbid")

    engine_version: str
    threshold_bundle_version: str
    registry_version: str
    signal_schema_version: str


class ReplayCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    tenant_id: str
    campaign_id: str
    input_payload: dict[str, Any]
    expected_output: dict[str, Any]
    version_tuple: VersionTuple


class DriftEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    tenant_id: str
    campaign_id: str
    drift_type: Literal["hash", "ordering", "confidence_band", "payload"]
    expected: str | list[str]
    actual: str | list[str]
    diff: str | None = None
    detected_at: datetime = Field(default_factory=datetime.utcnow)


class ReplayReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    corpus_version: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    drift_events: list[DriftEvent]
    generated_at: datetime = Field(default_factory=datetime.utcnow)
