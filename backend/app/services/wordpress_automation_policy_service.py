from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, time
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from app.models.recommendation_execution import RecommendationExecution
from app.models.wordpress_automation_policy import WordPressAutomationPolicy
from app.services.wordpress_connection_service import get_site_connection


SUPPORTED_WORDPRESS_AUTOMATION_ACTIONS = frozenset(
    {
        "create_content_brief",
        "fix_missing_title",
        "improve_internal_links",
        "publish_schema_markup",
    }
)
DEFAULT_SCHEDULE_DAYS = [0, 1, 2, 3, 4, 5, 6]


class WordPressAutomationPolicyError(RuntimeError):
    def __init__(self, message: str, *, reason_code: str, status_code: int = 409) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.status_code = status_code


@dataclass(frozen=True)
class WordPressAutomationDecision:
    allowed: bool
    reason_code: str
    message: str
    policy_version: int | None
    requires_manual_approval: bool = True
    actions_used_this_month: int = 0
    monthly_action_limit: int = 0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def get_wordpress_automation_policy(
    db: Session, *, campaign_id: str
) -> WordPressAutomationPolicy | None:
    return (
        db.query(WordPressAutomationPolicy)
        .filter(WordPressAutomationPolicy.campaign_id == campaign_id)
        .first()
    )


def serialize_wordpress_automation_policy(
    policy: WordPressAutomationPolicy | None,
    *,
    campaign_id: str,
) -> dict[str, Any]:
    if policy is None:
        return {
            "id": None,
            "campaign_id": campaign_id,
            "automation_enabled": False,
            "emergency_stop": False,
            "allowed_action_types": [],
            "allowed_url_prefixes": [],
            "schedule_timezone": "UTC",
            "schedule_days": DEFAULT_SCHEDULE_DAYS,
            "window_start_local": "00:00",
            "window_end_local": "23:59",
            "blackout_windows": [],
            "monthly_action_limit": 0,
            "risk_tier_ceiling": 1,
            "requires_manual_approval": True,
            "acknowledged_by": None,
            "acknowledged_at": None,
            "version": 0,
            "created_at": None,
            "updated_at": None,
            "safe_default": True,
        }
    return {
        "id": policy.id,
        "campaign_id": policy.campaign_id,
        "automation_enabled": bool(policy.automation_enabled),
        "emergency_stop": bool(policy.emergency_stop),
        "allowed_action_types": list(policy.allowed_action_types or []),
        "allowed_url_prefixes": list(policy.allowed_url_prefixes or []),
        "schedule_timezone": policy.schedule_timezone,
        "schedule_days": list(policy.schedule_days or []),
        "window_start_local": policy.window_start_local,
        "window_end_local": policy.window_end_local,
        "blackout_windows": list(policy.blackout_windows or []),
        "monthly_action_limit": int(policy.monthly_action_limit),
        "risk_tier_ceiling": int(policy.risk_tier_ceiling),
        "requires_manual_approval": bool(policy.requires_manual_approval),
        "acknowledged_by": policy.acknowledged_by,
        "acknowledged_at": (
            policy.acknowledged_at.isoformat() if policy.acknowledged_at else None
        ),
        "version": int(policy.version),
        "created_at": policy.created_at.isoformat() if policy.created_at else None,
        "updated_at": policy.updated_at.isoformat() if policy.updated_at else None,
        "safe_default": False,
    }


def save_wordpress_automation_policy(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
    actor_user_id: str,
    values: dict[str, Any],
) -> WordPressAutomationPolicy:
    normalized = _normalize_policy_values(db, campaign_id=campaign_id, values=values)
    row = get_wordpress_automation_policy(db, campaign_id=campaign_id)
    now = datetime.now(UTC)
    if row is None:
        row = WordPressAutomationPolicy(
            tenant_id=tenant_id,
            organization_id=organization_id,
            campaign_id=campaign_id,
            version=1,
            created_at=now,
        )
        db.add(row)
    else:
        row.version = int(row.version or 0) + 1
    for field_name, value in normalized.items():
        setattr(row, field_name, value)
    row.acknowledged_by = actor_user_id
    row.acknowledged_at = now
    row.updated_at = now
    db.flush()
    return row


def evaluate_wordpress_automation(
    db: Session,
    *,
    campaign_id: str,
    execution_type: str,
    risk_tier: int,
    affected_urls: list[str] | None = None,
    at: datetime | None = None,
) -> WordPressAutomationDecision:
    policy = get_wordpress_automation_policy(db, campaign_id=campaign_id)
    if policy is None or not policy.automation_enabled:
        return _deny(
            "wordpress_automation_not_enabled",
            "Managed website updates are off for this business.",
            policy,
        )
    connection = get_site_connection(db, campaign_id=campaign_id)
    if connection is None or connection.status != "connected":
        return _deny(
            "wordpress_site_connection_required",
            "Managed website updates are paused until WordPress is connected again.",
            policy,
        )
    if policy.emergency_stop:
        return _deny(
            "wordpress_automation_emergency_stop",
            "Managed website updates are paused by the emergency stop.",
            policy,
        )
    if execution_type not in set(policy.allowed_action_types or []):
        return _deny(
            "wordpress_automation_action_not_allowed",
            "This kind of website update is not allowed by the saved policy.",
            policy,
        )
    if int(risk_tier) > int(policy.risk_tier_ceiling):
        return _deny(
            "wordpress_automation_risk_too_high",
            "This website update is above the saved risk limit.",
            policy,
        )

    now = at or datetime.now(UTC)
    try:
        timezone = ZoneInfo(policy.schedule_timezone)
    except ZoneInfoNotFoundError:
        return _deny(
            "wordpress_automation_timezone_invalid",
            "The saved automation timezone is no longer valid.",
            policy,
        )
    local_now = now.astimezone(timezone)
    if local_now.weekday() not in set(int(day) for day in (policy.schedule_days or [])):
        return _deny(
            "wordpress_automation_outside_schedule",
            "This update is outside the allowed days.",
            policy,
        )
    if not _time_is_allowed(
        local_now.time(),
        start=_parse_local_time(policy.window_start_local),
        end=_parse_local_time(policy.window_end_local),
    ):
        return _deny(
            "wordpress_automation_outside_schedule",
            "This update is outside the allowed hours.",
            policy,
        )
    if _in_blackout_window(local_now, list(policy.blackout_windows or []), timezone):
        return _deny(
            "wordpress_automation_blackout_active",
            "Managed website updates are paused during a saved blackout window.",
            policy,
        )

    actions_used = _managed_actions_used_this_month(
        db,
        campaign_id=campaign_id,
        local_now=local_now,
        timezone=timezone,
    )
    if int(policy.monthly_action_limit) <= 0 or actions_used >= int(
        policy.monthly_action_limit
    ):
        return WordPressAutomationDecision(
            allowed=False,
            reason_code="wordpress_automation_monthly_limit",
            message="This business has reached its monthly managed-update limit.",
            policy_version=int(policy.version),
            requires_manual_approval=bool(policy.requires_manual_approval),
            actions_used_this_month=actions_used,
            monthly_action_limit=int(policy.monthly_action_limit),
        )

    if affected_urls is not None:
        prefixes = list(policy.allowed_url_prefixes or [])
        if not affected_urls or any(
            not _url_is_allowed(url, prefixes) for url in affected_urls
        ):
            return _deny(
                "wordpress_automation_url_not_allowed",
                "At least one website address is outside the saved work area.",
                policy,
                actions_used=actions_used,
            )

    return WordPressAutomationDecision(
        allowed=True,
        reason_code="wordpress_automation_allowed",
        message="This update is inside the saved managed-automation policy.",
        policy_version=int(policy.version),
        requires_manual_approval=bool(policy.requires_manual_approval),
        actions_used_this_month=actions_used,
        monthly_action_limit=int(policy.monthly_action_limit),
    )


def is_managed_wordpress_execution(execution: RecommendationExecution) -> bool:
    try:
        payload = json.loads(execution.execution_payload or "{}")
    except (json.JSONDecodeError, TypeError):
        return False
    return isinstance(payload, dict) and payload.get("managed_wordpress_automation") is True


def _normalize_policy_values(
    db: Session, *, campaign_id: str, values: dict[str, Any]
) -> dict[str, Any]:
    action_types = sorted(
        {str(value).strip() for value in values.get("allowed_action_types") or []}
    )
    unsupported = sorted(set(action_types) - SUPPORTED_WORDPRESS_AUTOMATION_ACTIONS)
    if unsupported:
        raise WordPressAutomationPolicyError(
            "One or more website action types are not supported.",
            reason_code="wordpress_automation_action_invalid",
            status_code=422,
        )
    timezone_name = str(values.get("schedule_timezone") or "UTC").strip()
    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise WordPressAutomationPolicyError(
            "Choose a valid timezone for managed website updates.",
            reason_code="wordpress_automation_timezone_invalid",
            status_code=422,
        ) from exc

    schedule_days = sorted({int(day) for day in values.get("schedule_days") or []})
    if any(day < 0 or day > 6 for day in schedule_days):
        raise WordPressAutomationPolicyError(
            "Schedule days must be between Monday (0) and Sunday (6).",
            reason_code="wordpress_automation_schedule_invalid",
            status_code=422,
        )
    start = str(values.get("window_start_local") or "00:00")
    end = str(values.get("window_end_local") or "23:59")
    _parse_local_time(start)
    _parse_local_time(end)

    connection = get_site_connection(db, campaign_id=campaign_id)
    prefixes = sorted(
        {
            _normalize_url_prefix(str(value))
            for value in values.get("allowed_url_prefixes") or []
            if str(value).strip()
        }
    )
    if connection is not None:
        expected_host = urlsplit(connection.site_url).hostname
        if any(urlsplit(prefix).hostname != expected_host for prefix in prefixes):
            raise WordPressAutomationPolicyError(
                "Every saved work area must belong to the connected WordPress website.",
                reason_code="wordpress_automation_url_scope_invalid",
                status_code=422,
            )

    automation_enabled = bool(values.get("automation_enabled"))
    monthly_action_limit = int(values.get("monthly_action_limit") or 0)
    if automation_enabled:
        if connection is None or connection.status != "connected":
            raise WordPressAutomationPolicyError(
                "Connect WordPress before turning on managed website updates.",
                reason_code="wordpress_site_connection_required",
            )
        if not action_types or not prefixes or not schedule_days or monthly_action_limit <= 0:
            raise WordPressAutomationPolicyError(
                "Choose at least one action, work area, schedule day, and monthly limit before turning this on.",
                reason_code="wordpress_automation_policy_incomplete",
                status_code=422,
            )

    blackouts = _normalize_blackouts(values.get("blackout_windows") or [])
    return {
        "automation_enabled": automation_enabled,
        "emergency_stop": bool(values.get("emergency_stop")),
        "allowed_action_types": action_types,
        "allowed_url_prefixes": prefixes,
        "schedule_timezone": timezone_name,
        "schedule_days": schedule_days,
        "window_start_local": start,
        "window_end_local": end,
        "blackout_windows": blackouts,
        "monthly_action_limit": monthly_action_limit,
        "risk_tier_ceiling": int(values.get("risk_tier_ceiling") or 1),
        "requires_manual_approval": bool(values.get("requires_manual_approval", True)),
    }


def _normalize_url_prefix(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise WordPressAutomationPolicyError(
            "Each work area must be a complete website address.",
            reason_code="wordpress_automation_url_scope_invalid",
            status_code=422,
        )
    path = parsed.path or "/"
    if not path.startswith("/"):
        path = f"/{path}"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, "", ""))


def _normalize_blackouts(values: list[Any]) -> list[dict[str, str]]:
    if len(values) > 24:
        raise WordPressAutomationPolicyError(
            "Save no more than 24 blackout windows.",
            reason_code="wordpress_automation_blackout_invalid",
            status_code=422,
        )
    normalized: list[dict[str, str]] = []
    for value in values:
        if not isinstance(value, dict):
            raise WordPressAutomationPolicyError(
                "Each blackout window needs a start and end time.",
                reason_code="wordpress_automation_blackout_invalid",
                status_code=422,
            )
        try:
            start = datetime.fromisoformat(str(value.get("start") or ""))
            end = datetime.fromisoformat(str(value.get("end") or ""))
        except ValueError as exc:
            raise WordPressAutomationPolicyError(
                "Each blackout window needs a valid start and end time.",
                reason_code="wordpress_automation_blackout_invalid",
                status_code=422,
            ) from exc
        if start.tzinfo is None or end.tzinfo is None or start >= end:
            raise WordPressAutomationPolicyError(
                "Each blackout window must have timezone-aware times in the correct order.",
                reason_code="wordpress_automation_blackout_invalid",
                status_code=422,
            )
        normalized.append(
            {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "label": str(value.get("label") or "Scheduled pause")[:120],
            }
        )
    return sorted(normalized, key=lambda item: item["start"])


def _parse_local_time(value: str) -> time:
    try:
        return time.fromisoformat(value)
    except ValueError as exc:
        raise WordPressAutomationPolicyError(
            "Allowed hours must use a 24-hour HH:MM time.",
            reason_code="wordpress_automation_schedule_invalid",
            status_code=422,
        ) from exc


def _time_is_allowed(current: time, *, start: time, end: time) -> bool:
    current_plain = current.replace(tzinfo=None)
    if start <= end:
        return start <= current_plain <= end
    return current_plain >= start or current_plain <= end


def _in_blackout_window(
    local_now: datetime, values: list[dict[str, Any]], timezone: ZoneInfo
) -> bool:
    for value in values:
        try:
            start = datetime.fromisoformat(str(value.get("start") or ""))
            end = datetime.fromisoformat(str(value.get("end") or ""))
        except ValueError:
            return True
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone)
        if start.astimezone(timezone) <= local_now <= end.astimezone(timezone):
            return True
    return False


def _managed_actions_used_this_month(
    db: Session,
    *,
    campaign_id: str,
    local_now: datetime,
    timezone: ZoneInfo,
) -> int:
    local_start = local_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    utc_start = local_start.astimezone(UTC)
    rows = (
        db.query(RecommendationExecution.execution_payload)
        .filter(
            RecommendationExecution.campaign_id == campaign_id,
            RecommendationExecution.created_at >= utc_start,
        )
        .all()
    )
    total = 0
    for row in rows:
        raw = row[0] if isinstance(row, tuple) else row.execution_payload
        try:
            payload = json.loads(raw or "{}")
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(payload, dict) and payload.get("managed_wordpress_automation") is True:
            total += 1
    return total


def _url_is_allowed(url: str, prefixes: list[str]) -> bool:
    target = urlsplit(url)
    for prefix in prefixes:
        allowed = urlsplit(prefix)
        if target.scheme.lower() != allowed.scheme.lower():
            continue
        if target.netloc.lower() != allowed.netloc.lower():
            continue
        allowed_path = allowed.path or "/"
        target_path = target.path or "/"
        if allowed_path == "/" or target_path == allowed_path or target_path.startswith(
            f"{allowed_path.rstrip('/')}/"
        ):
            return True
    return False


def _deny(
    reason_code: str,
    message: str,
    policy: WordPressAutomationPolicy | None,
    *,
    actions_used: int = 0,
) -> WordPressAutomationDecision:
    return WordPressAutomationDecision(
        allowed=False,
        reason_code=reason_code,
        message=message,
        policy_version=int(policy.version) if policy is not None else None,
        requires_manual_approval=(
            bool(policy.requires_manual_approval) if policy is not None else True
        ),
        actions_used_this_month=actions_used,
        monthly_action_limit=(int(policy.monthly_action_limit) if policy is not None else 0),
    )
