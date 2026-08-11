from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.business_location import BusinessLocation
from app.models.campaign import Campaign
from app.models.portfolio_targeting import (
    PortfolioLocationGroup,
    PortfolioLocationGroupMember,
    PortfolioTargetSnapshot,
)
from app.services.audit_service import write_audit_log


MAX_GROUP_LOCATIONS = 500
ALLOWED_GROUP_STATUSES = {"active", "archived"}


class PortfolioTargetingError(RuntimeError):
    def __init__(self, reason_code: str, *, status_code: int = 400) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code
        self.status_code = status_code


def list_location_groups(db: Session, *, organization_id: str) -> list[dict[str, Any]]:
    groups = (
        db.query(PortfolioLocationGroup)
        .filter(PortfolioLocationGroup.organization_id == organization_id)
        .order_by(
            PortfolioLocationGroup.status.asc(),
            PortfolioLocationGroup.name.asc(),
            PortfolioLocationGroup.id.asc(),
        )
        .all()
    )
    return [_serialize_group(db, group) for group in groups]


def create_location_group(
    db: Session,
    *,
    organization_id: str,
    actor_user_id: str,
    name: str,
    description: str | None,
    location_ids: list[str],
) -> PortfolioLocationGroup:
    normalized_name = _normalize_group_name(name)
    normalized_description = _normalize_optional(description)
    locations = _load_scoped_locations(
        db,
        organization_id=organization_id,
        location_ids=location_ids,
    )
    existing = (
        db.query(PortfolioLocationGroup.id)
        .filter(
            PortfolioLocationGroup.organization_id == organization_id,
            func.lower(PortfolioLocationGroup.name) == normalized_name.lower(),
        )
        .first()
    )
    if existing is not None:
        raise PortfolioTargetingError("location_group_name_conflict", status_code=409)

    now = datetime.now(UTC)
    group = PortfolioLocationGroup(
        id=str(uuid.uuid4()),
        tenant_id=organization_id,
        organization_id=organization_id,
        name=normalized_name,
        description=normalized_description,
        status="active",
        version=1,
        created_by_user_id=actor_user_id,
        created_at=now,
        updated_at=now,
    )
    db.add(group)
    db.flush()
    for location in locations:
        db.add(
            PortfolioLocationGroupMember(
                id=str(uuid.uuid4()),
                tenant_id=organization_id,
                organization_id=organization_id,
                location_group_id=group.id,
                business_location_id=location.id,
                added_by_user_id=actor_user_id,
                created_at=now,
            )
        )
    write_audit_log(
        db,
        tenant_id=organization_id,
        actor_user_id=actor_user_id,
        event_type="portfolio.location_group.created",
        payload={
            "organization_id": organization_id,
            "location_group_id": group.id,
            "name": group.name,
            "version": group.version,
            "location_ids": [location.id for location in locations],
        },
    )
    db.flush()
    return group


def update_location_group(
    db: Session,
    *,
    organization_id: str,
    location_group_id: str,
    actor_user_id: str,
    expected_version: int,
    name: str,
    description: str | None,
    status: str,
    location_ids: list[str],
) -> PortfolioLocationGroup:
    group = _load_group(
        db,
        organization_id=organization_id,
        location_group_id=location_group_id,
    )
    if group.version != expected_version:
        raise PortfolioTargetingError("location_group_version_conflict", status_code=409)
    if status not in ALLOWED_GROUP_STATUSES:
        raise PortfolioTargetingError("invalid_location_group_status")

    normalized_name = _normalize_group_name(name)
    normalized_description = _normalize_optional(description)
    duplicate = (
        db.query(PortfolioLocationGroup.id)
        .filter(
            PortfolioLocationGroup.organization_id == organization_id,
            PortfolioLocationGroup.id != group.id,
            func.lower(PortfolioLocationGroup.name) == normalized_name.lower(),
        )
        .first()
    )
    if duplicate is not None:
        raise PortfolioTargetingError("location_group_name_conflict", status_code=409)

    locations = _load_scoped_locations(
        db,
        organization_id=organization_id,
        location_ids=location_ids,
    )
    before = _serialize_group(db, group)
    db.query(PortfolioLocationGroupMember).filter(
        PortfolioLocationGroupMember.organization_id == organization_id,
        PortfolioLocationGroupMember.location_group_id == group.id,
    ).delete(synchronize_session=False)

    now = datetime.now(UTC)
    for location in locations:
        db.add(
            PortfolioLocationGroupMember(
                id=str(uuid.uuid4()),
                tenant_id=organization_id,
                organization_id=organization_id,
                location_group_id=group.id,
                business_location_id=location.id,
                added_by_user_id=actor_user_id,
                created_at=now,
            )
        )
    group.name = normalized_name
    group.description = normalized_description
    group.status = status
    group.version += 1
    group.updated_at = now
    db.flush()
    write_audit_log(
        db,
        tenant_id=organization_id,
        actor_user_id=actor_user_id,
        event_type="portfolio.location_group.updated",
        payload={
            "organization_id": organization_id,
            "location_group_id": group.id,
            "before": before,
            "after": _serialize_group(db, group),
        },
    )
    db.flush()
    return group


def serialize_location_group(
    db: Session, group: PortfolioLocationGroup
) -> dict[str, Any]:
    return _serialize_group(db, group)


def list_target_snapshots(
    db: Session,
    *,
    organization_id: str,
    limit: int,
) -> list[dict[str, Any]]:
    rows = (
        db.query(PortfolioTargetSnapshot)
        .filter(PortfolioTargetSnapshot.organization_id == organization_id)
        .order_by(
            PortfolioTargetSnapshot.created_at.desc(),
            PortfolioTargetSnapshot.id.desc(),
        )
        .limit(limit)
        .all()
    )
    return [serialize_target_snapshot(row) for row in rows]


def create_target_snapshot(
    db: Session,
    *,
    organization_id: str,
    actor_user_id: str,
    action_key: str,
    request_key: str,
    location_group_id: str | None,
    select_all_active: bool,
    regions: list[str],
    included_location_ids: list[str],
    excluded_location_ids: list[str],
) -> tuple[PortfolioTargetSnapshot, bool]:
    normalized_action_key = _normalize_key(action_key, field="action_key", max_length=80)
    normalized_request_key = _normalize_key(request_key, field="request_key", max_length=120)
    if location_group_id and select_all_active:
        raise PortfolioTargetingError("ambiguous_target_selection")
    if not location_group_id and not select_all_active and not included_location_ids:
        raise PortfolioTargetingError("explicit_target_selection_required")
    if regions and not location_group_id and not select_all_active:
        raise PortfolioTargetingError("region_filter_requires_base_selection")

    included = _load_scoped_locations(
        db,
        organization_id=organization_id,
        location_ids=included_location_ids,
    )
    excluded = _load_scoped_locations(
        db,
        organization_id=organization_id,
        location_ids=excluded_location_ids,
    )
    included_by_id = {location.id: location for location in included}
    excluded_by_id = {location.id: location for location in excluded}
    if included_by_id.keys() & excluded_by_id.keys():
        raise PortfolioTargetingError("location_cannot_be_included_and_excluded")

    group: PortfolioLocationGroup | None = None
    if location_group_id:
        group = _load_group(
            db,
            organization_id=organization_id,
            location_group_id=location_group_id,
        )
        if group.status != "active":
            raise PortfolioTargetingError("location_group_not_active", status_code=409)
        member_ids = [
            row.business_location_id
            for row in db.query(PortfolioLocationGroupMember)
            .filter(
                PortfolioLocationGroupMember.organization_id == organization_id,
                PortfolioLocationGroupMember.location_group_id == group.id,
            )
            .order_by(PortfolioLocationGroupMember.business_location_id.asc())
            .all()
        ]
        base_locations = _load_scoped_locations(
            db,
            organization_id=organization_id,
            location_ids=member_ids,
        )
        selection_mode = "group"
    elif select_all_active:
        base_locations = (
            db.query(BusinessLocation)
            .filter(
                BusinessLocation.organization_id == organization_id,
                BusinessLocation.status == "active",
            )
            .order_by(BusinessLocation.name.asc(), BusinessLocation.id.asc())
            .all()
        )
        selection_mode = "all_active"
    else:
        base_locations = []
        selection_mode = "explicit"

    normalized_regions = sorted(
        {region.strip() for region in regions if region and region.strip()},
        key=str.casefold,
    )
    region_keys = {region.casefold() for region in normalized_regions}
    exceptions: list[dict[str, Any]] = []
    candidate_by_id: dict[str, BusinessLocation] = {}
    for location in base_locations:
        if region_keys and (location.region or "").casefold() not in region_keys:
            exceptions.append(
                _location_exception(
                    location,
                    reason="outside_selected_regions",
                    message="Outside the selected work area.",
                    blocked=False,
                )
            )
            continue
        candidate_by_id[location.id] = location
    candidate_by_id.update(included_by_id)
    if included_by_id:
        exceptions = [
            item for item in exceptions if item["location_id"] not in included_by_id
        ]

    for location_id, location in excluded_by_id.items():
        candidate_by_id.pop(location_id, None)
        exceptions = [
            item for item in exceptions if item["location_id"] != location_id
        ]
        exceptions.append(
            _location_exception(
                location,
                reason="explicitly_excluded",
                message="Left out of this target list by an administrator.",
                blocked=False,
            )
        )

    campaign_rows = (
        db.query(Campaign)
        .filter(
            Campaign.organization_id == organization_id,
            Campaign.business_location_id.in_(list(candidate_by_id))
            if candidate_by_id
            else False,
        )
        .order_by(Campaign.created_at.desc(), Campaign.id.asc())
        .all()
    )
    campaign_by_location: dict[str, Campaign] = {}
    for campaign in campaign_rows:
        if campaign.business_location_id:
            campaign_by_location.setdefault(campaign.business_location_id, campaign)

    targets: list[dict[str, Any]] = []
    for location in sorted(
        candidate_by_id.values(), key=lambda item: (item.name.casefold(), item.id)
    ):
        if location.status != "active":
            exceptions.append(
                _location_exception(
                    location,
                    reason="location_not_active",
                    message="This location is not active.",
                    blocked=True,
                )
            )
            continue
        campaign = campaign_by_location.get(location.id)
        if campaign is None:
            exceptions.append(
                _location_exception(
                    location,
                    reason="campaign_missing",
                    message="Finish setting up this location before including it.",
                    blocked=True,
                )
            )
            continue
        targets.append(_target_item(location, campaign))

    exceptions.sort(key=lambda item: (str(item["location_name"]).casefold(), item["reason"]))
    selection = {
        "location_group_id": group.id if group else None,
        "location_group_version": group.version if group else None,
        "select_all_active": select_all_active,
        "regions": normalized_regions,
        "included_location_ids": sorted(included_by_id),
        "excluded_location_ids": sorted(excluded_by_id),
    }
    fingerprint_payload = {
        "action_key": normalized_action_key,
        "selection_mode": selection_mode,
        "selection": selection,
        "targets": targets,
        "exceptions": exceptions,
    }
    target_hash = hashlib.sha256(
        json.dumps(
            fingerprint_payload,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()

    existing = (
        db.query(PortfolioTargetSnapshot)
        .filter(
            PortfolioTargetSnapshot.organization_id == organization_id,
            PortfolioTargetSnapshot.request_key == normalized_request_key,
        )
        .first()
    )
    if existing is not None:
        if existing.target_hash != target_hash:
            raise PortfolioTargetingError("target_request_key_conflict", status_code=409)
        return existing, False

    row = PortfolioTargetSnapshot(
        id=str(uuid.uuid4()),
        tenant_id=organization_id,
        organization_id=organization_id,
        location_group_id=group.id if group else None,
        location_group_version=group.version if group else None,
        action_key=normalized_action_key,
        request_key=normalized_request_key,
        selection_mode=selection_mode,
        selection_json=selection,
        targets_json=targets,
        exceptions_json=exceptions,
        target_hash=target_hash,
        target_count=len(targets),
        blocked_count=sum(1 for item in exceptions if item["blocked"]),
        created_by_user_id=actor_user_id,
        created_at=datetime.now(UTC),
    )
    db.add(row)
    write_audit_log(
        db,
        tenant_id=organization_id,
        actor_user_id=actor_user_id,
        event_type="portfolio.target_snapshot.created",
        payload={
            "organization_id": organization_id,
            "target_snapshot_id": row.id,
            "location_group_id": row.location_group_id,
            "location_group_version": row.location_group_version,
            "action_key": row.action_key,
            "target_hash": row.target_hash,
            "target_count": row.target_count,
            "blocked_count": row.blocked_count,
        },
    )
    db.flush()
    return row, True


def serialize_target_snapshot(row: PortfolioTargetSnapshot) -> dict[str, Any]:
    return {
        "id": row.id,
        "organization_id": row.organization_id,
        "location_group_id": row.location_group_id,
        "location_group_version": row.location_group_version,
        "action_key": row.action_key,
        "request_key": row.request_key,
        "selection_mode": row.selection_mode,
        "selection": row.selection_json,
        "targets": row.targets_json,
        "exceptions": row.exceptions_json,
        "target_hash": row.target_hash,
        "target_count": row.target_count,
        "blocked_count": row.blocked_count,
        "created_by_user_id": row.created_by_user_id,
        "created_at": row.created_at.isoformat(),
        "immutable": True,
    }


def _serialize_group(db: Session, group: PortfolioLocationGroup) -> dict[str, Any]:
    rows = (
        db.query(BusinessLocation)
        .join(
            PortfolioLocationGroupMember,
            PortfolioLocationGroupMember.business_location_id == BusinessLocation.id,
        )
        .filter(
            PortfolioLocationGroupMember.organization_id == group.organization_id,
            PortfolioLocationGroupMember.location_group_id == group.id,
            BusinessLocation.organization_id == group.organization_id,
        )
        .order_by(BusinessLocation.name.asc(), BusinessLocation.id.asc())
        .all()
    )
    members = [
        {
            "location_id": location.id,
            "name": location.name,
            "city": location.city or location.primary_city,
            "region": location.region,
            "status": location.status,
        }
        for location in rows
    ]
    return {
        "id": group.id,
        "organization_id": group.organization_id,
        "name": group.name,
        "description": group.description,
        "status": group.status,
        "version": group.version,
        "member_count": len(members),
        "members": members,
        "created_by_user_id": group.created_by_user_id,
        "created_at": group.created_at.isoformat(),
        "updated_at": group.updated_at.isoformat(),
    }


def _load_group(
    db: Session,
    *,
    organization_id: str,
    location_group_id: str,
) -> PortfolioLocationGroup:
    row = (
        db.query(PortfolioLocationGroup)
        .filter(
            PortfolioLocationGroup.organization_id == organization_id,
            PortfolioLocationGroup.id == location_group_id,
        )
        .first()
    )
    if row is None:
        raise PortfolioTargetingError("location_group_not_found", status_code=404)
    return row


def _load_scoped_locations(
    db: Session,
    *,
    organization_id: str,
    location_ids: list[str],
) -> list[BusinessLocation]:
    unique_ids = sorted({item.strip() for item in location_ids if item and item.strip()})
    if len(unique_ids) > MAX_GROUP_LOCATIONS:
        raise PortfolioTargetingError("too_many_locations")
    if not unique_ids:
        return []
    rows = (
        db.query(BusinessLocation)
        .filter(
            BusinessLocation.organization_id == organization_id,
            BusinessLocation.id.in_(unique_ids),
        )
        .order_by(BusinessLocation.name.asc(), BusinessLocation.id.asc())
        .all()
    )
    if {row.id for row in rows} != set(unique_ids):
        raise PortfolioTargetingError("one_or_more_locations_unavailable", status_code=403)
    return rows


def _target_item(location: BusinessLocation, campaign: Campaign) -> dict[str, Any]:
    return {
        "location_id": location.id,
        "location_name": location.name,
        "city": location.city or location.primary_city,
        "region": location.region,
        "status": location.status,
        "campaign_id": campaign.id,
        "campaign_name": campaign.name,
    }


def _location_exception(
    location: BusinessLocation,
    *,
    reason: str,
    message: str,
    blocked: bool,
) -> dict[str, Any]:
    return {
        "location_id": location.id,
        "location_name": location.name,
        "city": location.city or location.primary_city,
        "region": location.region,
        "status": location.status,
        "reason": reason,
        "message": message,
        "blocked": blocked,
    }


def _normalize_group_name(value: str) -> str:
    normalized = " ".join(value.split())
    if not normalized or len(normalized) > 160:
        raise PortfolioTargetingError("invalid_location_group_name")
    return normalized


def _normalize_optional(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.split())
    return normalized or None


def _normalize_key(value: str, *, field: str, max_length: int) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > max_length:
        raise PortfolioTargetingError(f"invalid_{field}")
    if not all(character.isalnum() or character in "-_.:" for character in normalized):
        raise PortfolioTargetingError(f"invalid_{field}")
    return normalized
