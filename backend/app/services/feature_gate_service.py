from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, status

from app.models.organization import Organization


@dataclass(frozen=True)
class FeatureGate:
    enabled: bool
    limit: int | None = None


PLAN_LEVELS: dict[str, int] = {
    "standard": 1,
    "pro": 2,
    "enterprise": 3,
    "internal_anchor": 4,
}

FEATURE_RULES: dict[str, FeatureGate] = {
    "performance_trend": FeatureGate(enabled=True),
    "campaign_report": FeatureGate(enabled=True),
    "report_export": FeatureGate(enabled=True),
    "subaccount_limit": FeatureGate(enabled=True),
}

SUBACCOUNT_LIMIT_BY_LEVEL: dict[int, int] = {
    1: 3,   # standard
    2: 20,  # pro
    3: 100,  # enterprise
    4: 1000,  # internal anchor
}


def has_feature(org: Organization, feature_name: str) -> bool:
    plan_level = _plan_level(org.plan_type)
    if feature_name in {"performance_trend", "campaign_report"}:
        return plan_level >= PLAN_LEVELS["pro"]
    if feature_name == "report_export":
        return plan_level >= PLAN_LEVELS["enterprise"]
    if feature_name == "subaccount_limit":
        return True
    return False


def subaccount_limit(org: Organization) -> int:
    return SUBACCOUNT_LIMIT_BY_LEVEL.get(_plan_level(org.plan_type), SUBACCOUNT_LIMIT_BY_LEVEL[PLAN_LEVELS["standard"]])


def assert_feature_available(*, org: Organization, feature_name: str) -> None:
    if has_feature(org, feature_name):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "message": "Feature not available for current plan.",
            "reason_code": "feature_not_available",
            "feature_name": feature_name,
            "plan_type": org.plan_type,
        },
    )


def _plan_level(plan_type: str) -> int:
    return PLAN_LEVELS.get(plan_type.strip().lower(), PLAN_LEVELS["standard"])
