from __future__ import annotations

from typing import Any, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field, StrictInt, TypeAdapter


class RecommendationPayload(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    policy_id: str = Field(min_length=1)
    recommendation_type: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: dict[str, Any]
    risk_tier: StrictInt = Field(ge=0, le=4)
    rollback_plan: dict[str, Any]


class RecommendationBundle(BaseModel):
    model_config = ConfigDict(extra='forbid')

    recommendations: list[RecommendationPayload]


_RECOMMENDATION_LIST = TypeAdapter(list[RecommendationPayload])
_SENTINEL_KEYS = {'policy_id', 'recommendation_type', 'rollback_plan'}


def validate_recommendation_payload(payload: Mapping[str, Any] | RecommendationPayload) -> RecommendationPayload:
    if isinstance(payload, RecommendationPayload):
        return payload
    return RecommendationPayload.model_validate(dict(payload))


def validate_recommendation_payloads(payloads: Sequence[Mapping[str, Any] | RecommendationPayload]) -> list[RecommendationPayload]:
    normalized = [payload.model_dump(mode='json') if isinstance(payload, RecommendationPayload) else dict(payload) for payload in payloads]
    return _RECOMMENDATION_LIST.validate_python(normalized)


def maybe_validate_recommendation_artifact(payload: Mapping[str, Any]) -> dict[str, Any]:
    recommendations = payload.get('recommendations')
    if not isinstance(recommendations, list):
        return dict(payload)

    should_validate = any(isinstance(item, Mapping) and any(key in item for key in _SENTINEL_KEYS) for item in recommendations)
    if not should_validate:
        return dict(payload)

    validated = validate_recommendation_payloads(recommendations)
    normalized = dict(payload)
    normalized['recommendations'] = [item.model_dump(mode='json') for item in validated]
    return normalized
