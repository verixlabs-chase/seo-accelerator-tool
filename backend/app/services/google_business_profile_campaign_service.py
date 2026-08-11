from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.models.business_location import BusinessLocation
from app.models.campaign import Campaign
from app.models.data_connection import DataConnection
from app.models.google_business_profile import GoogleBusinessProfileSnapshot
from app.models.google_business_profile_campaign import (
    GoogleBusinessProfileCampaign,
    GoogleBusinessProfileCampaignVariant,
)
from app.models.organization import Organization
from app.models.portfolio_targeting import PortfolioTargetSnapshot
from app.services.audit_service import write_audit_log
from app.services.cost_economics_service import CostEconomicsError, resolve_plan_economics


GOOGLE_BUSINESS_PROFILE_PROVIDER = "google_business_profile"
ACTION_KEYS = {
    "local_post": "gbp_local_post",
    "photo_upload": "gbp_photo_upload",
}
ALLOWED_PLACEHOLDERS = {
    "location_name",
    "city",
    "region",
    "phone",
    "website",
}
PLACEHOLDER_PATTERN = re.compile(r"\{([a-z_]+)\}")
SHA256_PATTERN = re.compile(r"^[a-fA-F0-9]{64}$")
ALLOWED_POST_TYPES = {"update", "event", "offer"}
ALLOWED_CTA_TYPES = {
    "none",
    "book",
    "order",
    "shop",
    "learn_more",
    "sign_up",
    "call",
}
ALLOWED_PHOTO_CATEGORIES = {"cover", "profile", "additional"}
ALLOWED_PHOTO_FORMATS = {"image/jpeg", "image/png"}


class ProfileCampaignError(RuntimeError):
    def __init__(self, reason_code: str, *, status_code: int = 400) -> None:
        self.reason_code = reason_code
        self.status_code = status_code
        super().__init__(reason_code)


def create_profile_campaign(
    db: Session,
    *,
    organization_id: str,
    actor_user_id: str,
    target_snapshot_id: str,
    request_key: str,
    name: str,
    action_type: str,
    payload_template: dict[str, Any],
    scheduled_for: datetime | None,
) -> tuple[GoogleBusinessProfileCampaign, bool]:
    _assert_bulk_feature_plan(db, organization_id=organization_id)
    normalized_request_key = _bounded_text(request_key, field="request_key", limit=120)
    normalized_name = _bounded_text(name, field="name", limit=160)
    normalized_action = action_type.strip().lower()
    if normalized_action not in ACTION_KEYS:
        raise ProfileCampaignError("profile_campaign_action_not_supported", status_code=422)
    normalized_payload = _normalize_payload(normalized_action, payload_template)
    normalized_schedule = _normalize_schedule(scheduled_for)
    snapshot = _snapshot_or_error(
        db,
        organization_id=organization_id,
        target_snapshot_id=target_snapshot_id,
    )
    if snapshot.action_key != ACTION_KEYS[normalized_action]:
        raise ProfileCampaignError("profile_campaign_target_action_mismatch", status_code=409)

    content_hash = _fingerprint(
        {
            "action_type": normalized_action,
            "payload_template": normalized_payload,
            "scheduled_for": normalized_schedule.isoformat() if normalized_schedule else None,
            "target_hash": snapshot.target_hash,
        }
    )
    existing = (
        db.query(GoogleBusinessProfileCampaign)
        .filter(
            GoogleBusinessProfileCampaign.organization_id == organization_id,
            GoogleBusinessProfileCampaign.request_key == normalized_request_key,
        )
        .first()
    )
    if existing is not None:
        if (
            existing.target_snapshot_id != snapshot.id
            or existing.content_hash != content_hash
            or existing.action_type != normalized_action
        ):
            raise ProfileCampaignError("profile_campaign_request_key_conflict", status_code=409)
        return existing, False

    now = datetime.now(UTC)
    row = GoogleBusinessProfileCampaign(
        id=str(uuid.uuid4()),
        tenant_id=organization_id,
        organization_id=organization_id,
        target_snapshot_id=snapshot.id,
        name=normalized_name,
        action_type=normalized_action,
        request_key=normalized_request_key,
        status="draft",
        payload_template_json=normalized_payload,
        target_hash=snapshot.target_hash,
        content_hash=content_hash,
        approval_hash=None,
        preflight_json={},
        scheduled_for=normalized_schedule,
        ready_count=0,
        blocked_count=0,
        version=1,
        created_by_user_id=actor_user_id,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    write_audit_log(
        db,
        tenant_id=organization_id,
        actor_user_id=actor_user_id,
        event_type="google_business_profile.profile_campaign.created",
        payload={
            "organization_id": organization_id,
            "profile_campaign_id": row.id,
            "target_snapshot_id": snapshot.id,
            "target_hash": snapshot.target_hash,
            "content_hash": content_hash,
            "action_type": normalized_action,
            "provider_mutation": False,
        },
    )
    db.flush()
    return row, True


def run_profile_campaign_preflight(
    db: Session,
    *,
    organization_id: str,
    profile_campaign_id: str,
    actor_user_id: str,
    expected_version: int,
) -> GoogleBusinessProfileCampaign:
    row = _locked_campaign_or_error(
        db,
        organization_id=organization_id,
        profile_campaign_id=profile_campaign_id,
    )
    _assert_bulk_feature_plan(db, organization_id=organization_id)
    if row.version != expected_version:
        raise ProfileCampaignError("profile_campaign_version_conflict", status_code=409)
    if row.status not in {"draft", "awaiting_approval", "blocked"}:
        raise ProfileCampaignError("profile_campaign_preflight_locked", status_code=409)

    snapshot = _snapshot_or_error(
        db,
        organization_id=organization_id,
        target_snapshot_id=row.target_snapshot_id,
    )
    if snapshot.target_hash != row.target_hash:
        raise ProfileCampaignError("profile_campaign_target_changed", status_code=409)

    db.query(GoogleBusinessProfileCampaignVariant).filter(
        GoogleBusinessProfileCampaignVariant.organization_id == organization_id,
        GoogleBusinessProfileCampaignVariant.profile_campaign_id == row.id,
    ).delete(synchronize_session=False)

    variants: list[GoogleBusinessProfileCampaignVariant] = []
    for target in list(snapshot.targets_json or []):
        variants.append(_build_variant(db, profile_campaign=row, target=target))
    db.add_all(variants)
    db.flush()

    ready = [item for item in variants if item.status == "ready"]
    blocked = [item for item in variants if item.status == "blocked"]
    frozen_blocked = [
        dict(item)
        for item in list(snapshot.exceptions_json or [])
        if bool(item.get("blocked"))
    ]
    approval_hash = _approval_hash(row=row, variants=variants)
    now = datetime.now(UTC)
    row.ready_count = len(ready)
    row.blocked_count = len(blocked) + len(frozen_blocked)
    row.status = "awaiting_approval" if ready else "blocked"
    row.approval_hash = approval_hash
    row.preflight_json = {
        "checked_at": now.isoformat(),
        "target_snapshot": {
            "id": snapshot.id,
            "hash": snapshot.target_hash,
            "immutable": True,
        },
        "content_hash": row.content_hash,
        "approval_hash": approval_hash,
        "ready_count": len(ready),
        "blocked_count": len(blocked) + len(frozen_blocked),
        "frozen_target_exceptions": frozen_blocked,
        "provider_changes_enabled": False,
        "release_gate": (
            "Publishing stays locked until a supported action succeeds on one owned profile "
            "and the production Google quota is reviewed."
        ),
    }
    row.updated_at = now
    row.version += 1
    write_audit_log(
        db,
        tenant_id=organization_id,
        actor_user_id=actor_user_id,
        event_type="google_business_profile.profile_campaign.preflight_completed",
        payload={
            "organization_id": organization_id,
            "profile_campaign_id": row.id,
            "target_hash": row.target_hash,
            "content_hash": row.content_hash,
            "approval_hash": approval_hash,
            "ready_count": row.ready_count,
            "blocked_count": row.blocked_count,
            "provider_mutation": False,
        },
    )
    db.flush()
    return row


def approve_profile_campaign_hold(
    db: Session,
    *,
    organization_id: str,
    profile_campaign_id: str,
    actor_user_id: str,
    expected_version: int,
) -> GoogleBusinessProfileCampaign:
    row = _locked_campaign_or_error(
        db,
        organization_id=organization_id,
        profile_campaign_id=profile_campaign_id,
    )
    _assert_bulk_feature_plan(db, organization_id=organization_id)
    if row.version != expected_version:
        raise ProfileCampaignError("profile_campaign_version_conflict", status_code=409)
    if row.status != "awaiting_approval" or row.ready_count < 1:
        raise ProfileCampaignError("profile_campaign_not_ready_for_approval", status_code=409)
    variants = _variants(db, row.id)
    if row.approval_hash != _approval_hash(row=row, variants=variants):
        raise ProfileCampaignError("profile_campaign_approval_snapshot_changed", status_code=409)

    now = datetime.now(UTC)
    row.status = "approved_hold"
    row.approved_by_user_id = actor_user_id
    row.approved_at = now
    row.updated_at = now
    row.version += 1
    write_audit_log(
        db,
        tenant_id=organization_id,
        actor_user_id=actor_user_id,
        event_type="google_business_profile.profile_campaign.approved_for_hold",
        payload={
            "organization_id": organization_id,
            "profile_campaign_id": row.id,
            "approval_hash": row.approval_hash,
            "ready_count": row.ready_count,
            "blocked_count": row.blocked_count,
            "provider_mutation": False,
            "dispatch_enabled": False,
        },
    )
    db.flush()
    return row


def list_profile_campaigns(
    db: Session,
    *,
    organization_id: str,
    limit: int = 20,
    location_group_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    query = db.query(GoogleBusinessProfileCampaign).filter(
        GoogleBusinessProfileCampaign.organization_id == organization_id
    )
    if location_group_ids is not None:
        if not location_group_ids:
            return []
        query = query.join(
            PortfolioTargetSnapshot,
            PortfolioTargetSnapshot.id == GoogleBusinessProfileCampaign.target_snapshot_id,
        ).filter(PortfolioTargetSnapshot.location_group_id.in_(location_group_ids))
    rows = query.order_by(
        GoogleBusinessProfileCampaign.created_at.desc(),
        GoogleBusinessProfileCampaign.id.desc(),
    ).limit(limit).all()
    return [serialize_profile_campaign(db, row) for row in rows]


def get_profile_campaign(
    db: Session,
    *,
    organization_id: str,
    profile_campaign_id: str,
) -> GoogleBusinessProfileCampaign:
    return _campaign_or_error(
        db,
        organization_id=organization_id,
        profile_campaign_id=profile_campaign_id,
    )


def serialize_profile_campaign(
    db: Session,
    row: GoogleBusinessProfileCampaign,
) -> dict[str, Any]:
    variants = _variants(db, row.id)
    snapshot = db.get(PortfolioTargetSnapshot, row.target_snapshot_id)
    targeted_count = (
        row.ready_count + row.blocked_count
        if variants
        else int(snapshot.target_count if snapshot else 0)
        + int(snapshot.blocked_count if snapshot else 0)
    )
    return {
        "id": row.id,
        "organization_id": row.organization_id,
        "target_snapshot_id": row.target_snapshot_id,
        "name": row.name,
        "action_type": row.action_type,
        "action_label": "Business update" if row.action_type == "local_post" else "Photo upload",
        "request_key": row.request_key,
        "status": row.status,
        "status_label": {
            "draft": "Draft",
            "awaiting_approval": "Ready for approval",
            "blocked": "Needs setup",
            "approved_hold": "Approved — publishing locked",
            "cancelled": "Cancelled",
        }.get(row.status, row.status.replace("_", " ").title()),
        "payload_template": row.payload_template_json,
        "target_hash": row.target_hash,
        "content_hash": row.content_hash,
        "approval_hash": row.approval_hash,
        "preflight": row.preflight_json,
        "scheduled_for": row.scheduled_for.isoformat() if row.scheduled_for else None,
        "counts": {
            "targeted": targeted_count,
            "ready": row.ready_count,
            "blocked": row.blocked_count,
        },
        "approval": {
            "required": True,
            "approved": row.approved_at is not None,
            "approved_by_user_id": row.approved_by_user_id,
            "approved_at": row.approved_at.isoformat() if row.approved_at else None,
            "immutable_snapshot": row.approval_hash is not None,
        },
        "variants": [_serialize_variant(item) for item in variants],
        "provider_changes_enabled": False,
        "can_preflight": row.status in {"draft", "awaiting_approval", "blocked"},
        "can_approve": row.status == "awaiting_approval" and row.ready_count > 0,
        "version": row.version,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def _build_variant(
    db: Session,
    *,
    profile_campaign: GoogleBusinessProfileCampaign,
    target: dict[str, Any],
) -> GoogleBusinessProfileCampaignVariant:
    organization_id = profile_campaign.organization_id
    location_id = str(target.get("location_id") or "")
    campaign_id = str(target.get("campaign_id") or "")
    location_name = str(target.get("location_name") or "Location")
    location = (
        db.query(BusinessLocation)
        .filter(
            BusinessLocation.organization_id == organization_id,
            BusinessLocation.id == location_id,
        )
        .first()
    )
    campaign = (
        db.query(Campaign)
        .filter(
            Campaign.organization_id == organization_id,
            Campaign.id == campaign_id,
            Campaign.business_location_id == location_id,
        )
        .first()
    )
    connection = (
        db.query(DataConnection)
        .filter(
            DataConnection.organization_id == organization_id,
            DataConnection.business_location_id == location_id,
            DataConnection.campaign_id == campaign_id,
            DataConnection.provider_name == GOOGLE_BUSINESS_PROFILE_PROVIDER,
        )
        .first()
    )
    profile_snapshot = (
        db.query(GoogleBusinessProfileSnapshot)
        .filter(
            GoogleBusinessProfileSnapshot.organization_id == organization_id,
            GoogleBusinessProfileSnapshot.connection_id == connection.id,
        )
        .order_by(
            GoogleBusinessProfileSnapshot.captured_at.desc(),
            GoogleBusinessProfileSnapshot.id.desc(),
        )
        .first()
        if connection
        else None
    )
    facts = _location_facts(
        location=location,
        campaign=campaign,
        profile_data=profile_snapshot.profile_data if profile_snapshot else {},
    )
    rendered = _render_payload(profile_campaign.payload_template_json, facts)
    checks = [
        _check("location_active", location is not None and location.status == "active", "This location is active."),
        _check("workspace_matched", campaign is not None, "This location has its own workspace."),
        _check(
            "profile_mapped",
            connection is not None
            and connection.status == "connected"
            and str(connection.external_resource_id or "").startswith("locations/"),
            "An owned Google business listing is matched to this location.",
        ),
        _check(
            "profile_verified",
            bool(connection and (connection.connection_metadata or {}).get("profile_verified")),
            "Google shows this listing as verified.",
        ),
        _check(
            "permission_verified",
            bool(connection and (connection.connection_metadata or {}).get("permission_verified")),
            "The connected account can manage this listing.",
        ),
        _check(
            "single_profile_action_validated",
            bool(connection and (connection.connection_metadata or {}).get("mutation_enabled")),
            "A supported action has been validated on this owned listing.",
        ),
        _check(
            "location_facts_complete",
            not _missing_required_facts(profile_campaign.payload_template_json, facts),
            "Every location detail used by this draft is confirmed.",
        ),
        _check(
            "destination_safe",
            _rendered_destination_is_safe(rendered),
            "Every destination uses a secure website address.",
        ),
    ]
    failed = next((item for item in checks if not item["passed"]), None)
    payload_hash = _fingerprint(rendered)
    duplicate = (
        db.query(GoogleBusinessProfileCampaignVariant.id)
        .join(
            GoogleBusinessProfileCampaign,
            GoogleBusinessProfileCampaign.id
            == GoogleBusinessProfileCampaignVariant.profile_campaign_id,
        )
        .filter(
            GoogleBusinessProfileCampaign.organization_id == organization_id,
            GoogleBusinessProfileCampaign.id != profile_campaign.id,
            GoogleBusinessProfileCampaign.status == "approved_hold",
            GoogleBusinessProfileCampaignVariant.external_resource_id
            == (connection.external_resource_id if connection else None),
            GoogleBusinessProfileCampaignVariant.payload_hash == payload_hash,
        )
        .first()
    )
    if failed is None and duplicate is not None:
        failed = {
            "code": "duplicate_payload",
            "passed": False,
            "message": "This exact update is already part of an approved campaign for this listing.",
        }
        checks.append(failed)
    return GoogleBusinessProfileCampaignVariant(
        id=str(uuid.uuid4()),
        tenant_id=organization_id,
        organization_id=organization_id,
        profile_campaign_id=profile_campaign.id,
        business_location_id=location_id,
        campaign_id=campaign.id if campaign else None,
        connection_id=connection.id if connection else None,
        external_resource_id=connection.external_resource_id if connection else None,
        location_name=location.name if location else location_name,
        status="blocked" if failed else "ready",
        rendered_payload_json=rendered,
        checks_json=checks,
        payload_hash=payload_hash,
        reason_code=str(failed["code"]) if failed else None,
        reason_message=str(failed["message"]) if failed else None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _normalize_payload(action_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ProfileCampaignError("profile_campaign_payload_required", status_code=422)
    unknown_placeholders = _placeholders(payload) - ALLOWED_PLACEHOLDERS
    if unknown_placeholders:
        raise ProfileCampaignError("profile_campaign_unknown_placeholder", status_code=422)
    if action_type == "local_post":
        summary = _bounded_text(payload.get("summary"), field="summary", limit=1500)
        post_type = str(payload.get("post_type") or "update").strip().lower()
        if post_type not in ALLOWED_POST_TYPES:
            raise ProfileCampaignError("profile_campaign_post_type_not_supported", status_code=422)
        cta_type = str(payload.get("call_to_action") or "none").strip().lower()
        if cta_type not in ALLOWED_CTA_TYPES:
            raise ProfileCampaignError("profile_campaign_call_to_action_not_supported", status_code=422)
        destination_url = str(payload.get("destination_url") or "").strip()
        if cta_type not in {"none", "call"} and not destination_url:
            raise ProfileCampaignError("profile_campaign_destination_required", status_code=422)
        normalized: dict[str, Any] = {
            "post_type": post_type,
            "summary": summary,
            "call_to_action": cta_type,
            "destination_url": destination_url or None,
        }
        if post_type in {"event", "offer"}:
            normalized["title"] = _bounded_text(payload.get("title"), field="title", limit=80)
            normalized["starts_at"] = _bounded_text(payload.get("starts_at"), field="starts_at", limit=40)
            normalized["ends_at"] = _bounded_text(payload.get("ends_at"), field="ends_at", limit=40)
        if post_type == "offer":
            normalized["coupon_code"] = str(payload.get("coupon_code") or "").strip()[:80] or None
            normalized["terms"] = str(payload.get("terms") or "").strip()[:1000] or None
        return normalized

    asset_url = _bounded_text(payload.get("asset_url"), field="asset_url", limit=2000)
    parsed = urlparse(asset_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ProfileCampaignError("profile_campaign_secure_asset_required", status_code=422)
    checksum = _bounded_text(payload.get("checksum_sha256"), field="checksum_sha256", limit=64)
    if not SHA256_PATTERN.fullmatch(checksum):
        raise ProfileCampaignError("profile_campaign_asset_checksum_invalid", status_code=422)
    category = str(payload.get("category") or "additional").strip().lower()
    media_format = str(payload.get("media_format") or "").strip().lower()
    if category not in ALLOWED_PHOTO_CATEGORIES:
        raise ProfileCampaignError("profile_campaign_photo_category_not_supported", status_code=422)
    if media_format not in ALLOWED_PHOTO_FORMATS:
        raise ProfileCampaignError("profile_campaign_photo_format_not_supported", status_code=422)
    if payload.get("rights_confirmed") is not True:
        raise ProfileCampaignError("profile_campaign_asset_rights_required", status_code=422)
    return {
        "asset_url": asset_url,
        "checksum_sha256": checksum.lower(),
        "category": category,
        "media_format": media_format,
        "rights_confirmed": True,
        "context_note": str(payload.get("context_note") or "").strip()[:300] or None,
    }


def _normalize_schedule(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    normalized = value if value.tzinfo else value.replace(tzinfo=UTC)
    normalized = normalized.astimezone(UTC)
    if normalized <= datetime.now(UTC):
        raise ProfileCampaignError("profile_campaign_schedule_must_be_future", status_code=422)
    return normalized


def _location_facts(
    *,
    location: BusinessLocation | None,
    campaign: Campaign | None,
    profile_data: dict[str, Any],
) -> dict[str, str]:
    domain = str(
        profile_data.get("websiteUri")
        or (campaign.domain if campaign else None)
        or (location.domain if location else None)
        or ""
    ).strip()
    website = domain if domain.startswith(("http://", "https://")) else f"https://{domain}" if domain else ""
    phone_numbers = profile_data.get("phoneNumbers") or {}
    phone = (
        str(phone_numbers.get("primaryPhone") or "").strip()
        if isinstance(phone_numbers, dict)
        else ""
    )
    return {
        "location_name": str(location.name if location else "").strip(),
        "city": str((location.city or location.primary_city) if location else "").strip(),
        "region": str(location.region if location else "").strip(),
        "phone": phone,
        "website": website,
    }


def _render_payload(payload: dict[str, Any], facts: dict[str, str]) -> dict[str, Any]:
    def render(value: Any) -> Any:
        if isinstance(value, str):
            return PLACEHOLDER_PATTERN.sub(lambda match: facts.get(match.group(1), ""), value)
        if isinstance(value, dict):
            return {key: render(item) for key, item in value.items()}
        if isinstance(value, list):
            return [render(item) for item in value]
        return value

    return render(payload)


def _placeholders(value: Any) -> set[str]:
    if isinstance(value, str):
        return set(PLACEHOLDER_PATTERN.findall(value))
    if isinstance(value, dict):
        return set().union(*(_placeholders(item) for item in value.values()), set())
    if isinstance(value, list):
        return set().union(*(_placeholders(item) for item in value), set())
    return set()


def _missing_required_facts(payload: dict[str, Any], facts: dict[str, str]) -> list[str]:
    return sorted(key for key in _placeholders(payload) if not facts.get(key))


def _rendered_destination_is_safe(payload: dict[str, Any]) -> bool:
    for key in ("destination_url", "asset_url"):
        value = str(payload.get(key) or "").strip()
        if not value:
            continue
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.netloc:
            return False
    return True


def _check(code: str, passed: bool, success_message: str) -> dict[str, Any]:
    failure_messages = {
        "location_active": "Reactivate this location before including it.",
        "workspace_matched": "Finish this location's workspace setup first.",
        "profile_mapped": "Match this location to its owned Google business listing.",
        "profile_verified": "Finish verification of this Google business listing.",
        "permission_verified": "Reconnect with an account that can manage this listing.",
        "single_profile_action_validated": "Live profile actions have not been validated for this listing yet.",
        "location_facts_complete": "Add the missing location details used by this draft.",
        "destination_safe": "Use a secure https website address.",
    }
    return {
        "code": code,
        "passed": bool(passed),
        "message": success_message if passed else failure_messages[code],
    }


def _approval_hash(
    *,
    row: GoogleBusinessProfileCampaign,
    variants: list[GoogleBusinessProfileCampaignVariant],
) -> str:
    return _fingerprint(
        {
            "target_hash": row.target_hash,
            "content_hash": row.content_hash,
            "variants": [
                {
                    "business_location_id": item.business_location_id,
                    "external_resource_id": item.external_resource_id,
                    "status": item.status,
                    "payload_hash": item.payload_hash,
                }
                for item in sorted(variants, key=lambda item: item.business_location_id)
            ],
        }
    )


def _serialize_variant(item: GoogleBusinessProfileCampaignVariant) -> dict[str, Any]:
    return {
        "id": item.id,
        "business_location_id": item.business_location_id,
        "campaign_id": item.campaign_id,
        "connection_id": item.connection_id,
        "external_resource_id": item.external_resource_id,
        "location_name": item.location_name,
        "status": item.status,
        "status_label": "Ready" if item.status == "ready" else "Needs setup",
        "rendered_payload": item.rendered_payload_json,
        "checks": item.checks_json,
        "payload_hash": item.payload_hash,
        "reason_code": item.reason_code,
        "message": item.reason_message or "Ready for approval.",
    }


def _fingerprint(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _bounded_text(value: Any, *, field: str, limit: int) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ProfileCampaignError(f"profile_campaign_{field}_required", status_code=422)
    if len(normalized) > limit:
        raise ProfileCampaignError(f"profile_campaign_{field}_too_long", status_code=422)
    return normalized


def _snapshot_or_error(
    db: Session, *, organization_id: str, target_snapshot_id: str
) -> PortfolioTargetSnapshot:
    row = (
        db.query(PortfolioTargetSnapshot)
        .filter(
            PortfolioTargetSnapshot.organization_id == organization_id,
            PortfolioTargetSnapshot.id == target_snapshot_id,
        )
        .first()
    )
    if row is None:
        raise ProfileCampaignError("target_snapshot_not_found", status_code=404)
    return row


def _campaign_or_error(
    db: Session, *, organization_id: str, profile_campaign_id: str
) -> GoogleBusinessProfileCampaign:
    row = (
        db.query(GoogleBusinessProfileCampaign)
        .filter(
            GoogleBusinessProfileCampaign.organization_id == organization_id,
            GoogleBusinessProfileCampaign.id == profile_campaign_id,
        )
        .first()
    )
    if row is None:
        raise ProfileCampaignError("profile_campaign_not_found", status_code=404)
    return row


def _locked_campaign_or_error(
    db: Session, *, organization_id: str, profile_campaign_id: str
) -> GoogleBusinessProfileCampaign:
    row = (
        db.query(GoogleBusinessProfileCampaign)
        .filter(
            GoogleBusinessProfileCampaign.organization_id == organization_id,
            GoogleBusinessProfileCampaign.id == profile_campaign_id,
        )
        .with_for_update()
        .first()
    )
    if row is None:
        raise ProfileCampaignError("profile_campaign_not_found", status_code=404)
    return row


def _variants(db: Session, profile_campaign_id: str) -> list[GoogleBusinessProfileCampaignVariant]:
    return (
        db.query(GoogleBusinessProfileCampaignVariant)
        .filter(GoogleBusinessProfileCampaignVariant.profile_campaign_id == profile_campaign_id)
        .order_by(
            GoogleBusinessProfileCampaignVariant.location_name.asc(),
            GoogleBusinessProfileCampaignVariant.id.asc(),
        )
        .all()
    )


def _assert_bulk_feature_plan(db: Session, *, organization_id: str) -> None:
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise ProfileCampaignError("organization_not_found", status_code=404)
    try:
        plan = resolve_plan_economics(organization.plan_type)
    except CostEconomicsError as exc:
        raise ProfileCampaignError("profile_campaign_upgrade_required", status_code=403) from exc
    if plan.code not in {"multi_location", "enterprise"}:
        raise ProfileCampaignError("profile_campaign_upgrade_required", status_code=403)
