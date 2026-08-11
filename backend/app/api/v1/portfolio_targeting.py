from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import enforce_organization_scope, require_org_role
from app.api.response import envelope
from app.db.session import get_db
from app.models.portfolio_fleet_run import PortfolioFleetRun
from app.models.portfolio_targeting import PortfolioTargetSnapshot
from app.schemas.portfolio_targeting import (
    LocationGroupCreateIn,
    LocationGroupUpdateIn,
    PortfolioAccessGrantCreateIn,
    PortfolioAccessGrantDecisionIn,
    PortfolioFleetRunCreateIn,
    PortfolioFleetRunDecisionIn,
    TargetSnapshotCreateIn,
)
from app.services.portfolio_fleet_service import (
    PortfolioFleetError,
    approve_portfolio_fleet_run,
    create_portfolio_fleet_run,
    get_portfolio_fleet_run,
    list_portfolio_fleet_runs,
    pause_portfolio_fleet_run,
    resume_portfolio_fleet_run,
    retry_failed_portfolio_fleet_run_items,
    serialize_portfolio_fleet_run,
)
from app.services.portfolio_access_service import (
    PortfolioAccessError,
    accessible_location_group_ids,
    list_portfolio_access_grants,
    require_location_group_access,
    require_target_overrides_within_group,
    revoke_portfolio_access_grant,
    save_portfolio_access_grant,
    serialize_portfolio_access_grant,
)
from app.services.portfolio_targeting_service import (
    PortfolioTargetingError,
    create_location_group,
    create_target_snapshot,
    list_location_groups,
    list_target_snapshots,
    serialize_location_group,
    serialize_target_snapshot,
    update_location_group,
)


router = APIRouter(tags=["portfolio-targeting"])
owner_or_admin = require_org_role({"org_owner", "org_admin"})
portfolio_member = require_org_role({"org_user"})


@router.get("/organizations/{organization_id}/portfolio-access-grants")
def get_portfolio_access_grants(
    request: Request,
    organization_id: str,
    include_revoked: bool = Query(default=False),
    user: dict = Depends(owner_or_admin),
    db: Session = Depends(get_db),
) -> dict:
    _enforce_scope(user, organization_id)
    return envelope(
        request,
        {
            "items": list_portfolio_access_grants(
                db,
                organization_id=organization_id,
                include_revoked=include_revoked,
            )
        },
    )


@router.post(
    "/organizations/{organization_id}/portfolio-access-grants",
    status_code=status.HTTP_201_CREATED,
)
def post_portfolio_access_grant(
    request: Request,
    organization_id: str,
    body: PortfolioAccessGrantCreateIn,
    user: dict = Depends(owner_or_admin),
    db: Session = Depends(get_db),
) -> dict:
    _enforce_scope(user, organization_id)
    try:
        grant, created = save_portfolio_access_grant(
            db,
            organization_id=organization_id,
            actor_user_id=user["id"],
            grantee_email=body.grantee_email,
            location_group_id=body.location_group_id,
            access_role=body.access_role,
            expected_version=body.expected_version,
        )
        db.commit()
        db.refresh(grant)
    except PortfolioAccessError as exc:
        db.rollback()
        _raise_access_error(exc)
    response = envelope(
        request,
        {
            "portfolio_access_grant": serialize_portfolio_access_grant(db, grant),
            "created": created,
        },
    )
    return response


@router.post(
    "/organizations/{organization_id}/portfolio-access-grants/{grant_id}/revoke"
)
def post_portfolio_access_grant_revoke(
    request: Request,
    organization_id: str,
    grant_id: str,
    body: PortfolioAccessGrantDecisionIn,
    user: dict = Depends(owner_or_admin),
    db: Session = Depends(get_db),
) -> dict:
    _enforce_scope(user, organization_id)
    try:
        grant = revoke_portfolio_access_grant(
            db,
            organization_id=organization_id,
            grant_id=grant_id,
            actor_user_id=user["id"],
            expected_version=body.expected_version,
        )
        db.commit()
        db.refresh(grant)
    except PortfolioAccessError as exc:
        db.rollback()
        _raise_access_error(exc)
    return envelope(
        request,
        {"portfolio_access_grant": serialize_portfolio_access_grant(db, grant)},
    )


@router.get("/organizations/{organization_id}/location-groups")
def get_location_groups(
    request: Request,
    organization_id: str,
    user: dict = Depends(portfolio_member),
    db: Session = Depends(get_db),
) -> dict:
    _enforce_scope(user, organization_id)
    group_ids = _accessible_group_ids(db, user=user, organization_id=organization_id)
    return envelope(
        request,
        {
            "items": list_location_groups(
                db,
                organization_id=organization_id,
                location_group_ids=group_ids,
            )
        },
    )


@router.post(
    "/organizations/{organization_id}/location-groups",
    status_code=status.HTTP_201_CREATED,
)
def post_location_group(
    request: Request,
    organization_id: str,
    body: LocationGroupCreateIn,
    user: dict = Depends(owner_or_admin),
    db: Session = Depends(get_db),
) -> dict:
    _enforce_scope(user, organization_id)
    try:
        group = create_location_group(
            db,
            organization_id=organization_id,
            actor_user_id=user["id"],
            name=body.name,
            description=body.description,
            location_ids=body.location_ids,
        )
        db.commit()
        db.refresh(group)
    except PortfolioTargetingError as exc:
        db.rollback()
        _raise_targeting_error(exc)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "That saved group conflicts with an existing group.",
                "reason_code": "location_group_conflict",
            },
        ) from exc
    return envelope(request, {"location_group": serialize_location_group(db, group)})


@router.patch("/organizations/{organization_id}/location-groups/{location_group_id}")
def patch_location_group(
    request: Request,
    organization_id: str,
    location_group_id: str,
    body: LocationGroupUpdateIn,
    user: dict = Depends(owner_or_admin),
    db: Session = Depends(get_db),
) -> dict:
    _enforce_scope(user, organization_id)
    try:
        group = update_location_group(
            db,
            organization_id=organization_id,
            location_group_id=location_group_id,
            actor_user_id=user["id"],
            expected_version=body.expected_version,
            name=body.name,
            description=body.description,
            status=body.status,
            location_ids=body.location_ids,
        )
        db.commit()
        db.refresh(group)
    except PortfolioTargetingError as exc:
        db.rollback()
        _raise_targeting_error(exc)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "That saved group conflicts with an existing group.",
                "reason_code": "location_group_conflict",
            },
        ) from exc
    return envelope(request, {"location_group": serialize_location_group(db, group)})


@router.get("/organizations/{organization_id}/target-snapshots")
def get_target_snapshots(
    request: Request,
    organization_id: str,
    limit: int = Query(default=10, ge=1, le=50),
    user: dict = Depends(portfolio_member),
    db: Session = Depends(get_db),
) -> dict:
    _enforce_scope(user, organization_id)
    group_ids = _accessible_group_ids(db, user=user, organization_id=organization_id)
    return envelope(
        request,
        {
            "items": list_target_snapshots(
                db,
                organization_id=organization_id,
                limit=limit,
                location_group_ids=group_ids,
            )
        },
    )


@router.post(
    "/organizations/{organization_id}/target-snapshots",
    status_code=status.HTTP_201_CREATED,
)
def post_target_snapshot(
    request: Request,
    organization_id: str,
    body: TargetSnapshotCreateIn,
    user: dict = Depends(portfolio_member),
    db: Session = Depends(get_db),
) -> dict:
    _enforce_scope(user, organization_id)
    try:
        require_location_group_access(
            db,
            organization_id=organization_id,
            user_id=user["id"],
            org_role=str(user.get("org_role") or ""),
            location_group_id=body.location_group_id,
            required_access_role="operator",
        )
        require_target_overrides_within_group(
            db,
            organization_id=organization_id,
            org_role=str(user.get("org_role") or ""),
            location_group_id=body.location_group_id,
            included_location_ids=body.included_location_ids,
            excluded_location_ids=body.excluded_location_ids,
        )
        snapshot, created = create_target_snapshot(
            db,
            organization_id=organization_id,
            actor_user_id=user["id"],
            action_key=body.action_key,
            request_key=body.request_key,
            location_group_id=body.location_group_id,
            select_all_active=body.select_all_active,
            regions=body.regions,
            included_location_ids=body.included_location_ids,
            excluded_location_ids=body.excluded_location_ids,
        )
        db.commit()
        db.refresh(snapshot)
    except PortfolioTargetingError as exc:
        db.rollback()
        _raise_targeting_error(exc)
    except PortfolioAccessError as exc:
        db.rollback()
        _raise_access_error(exc)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "This target request was already used for a different list.",
                "reason_code": "target_request_key_conflict",
            },
        ) from exc
    response = envelope(
        request,
        {
            "target_snapshot": serialize_target_snapshot(snapshot),
            "created": created,
        },
    )
    if not created:
        response["meta"]["idempotent_replay"] = True
    return response


@router.get("/organizations/{organization_id}/portfolio-fleet-runs")
def get_portfolio_fleet_runs(
    request: Request,
    organization_id: str,
    limit: int = Query(default=10, ge=1, le=50),
    user: dict = Depends(portfolio_member),
    db: Session = Depends(get_db),
) -> dict:
    _enforce_scope(user, organization_id)
    group_ids = _accessible_group_ids(db, user=user, organization_id=organization_id)
    return envelope(
        request,
        {
            "items": list_portfolio_fleet_runs(
                db,
                organization_id=organization_id,
                limit=limit,
                location_group_ids=group_ids,
            )
        },
    )


@router.post(
    "/organizations/{organization_id}/portfolio-fleet-runs",
    status_code=status.HTTP_201_CREATED,
)
def post_portfolio_fleet_run(
    request: Request,
    organization_id: str,
    body: PortfolioFleetRunCreateIn,
    user: dict = Depends(portfolio_member),
    db: Session = Depends(get_db),
) -> dict:
    _enforce_scope(user, organization_id)
    try:
        _require_snapshot_access(
            db,
            user=user,
            organization_id=organization_id,
            target_snapshot_id=body.target_snapshot_id,
            required_access_role="operator",
        )
        run, created = create_portfolio_fleet_run(
            db,
            organization_id=organization_id,
            actor_user_id=user["id"],
            target_snapshot_id=body.target_snapshot_id,
            request_key=body.request_key,
        )
        db.commit()
        db.refresh(run)
    except PortfolioFleetError as exc:
        db.rollback()
        _raise_fleet_error(exc)
    except PortfolioAccessError as exc:
        db.rollback()
        _raise_access_error(exc)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "This bulk-work request was already used for a different target list.",
                "reason_code": "fleet_request_key_conflict",
            },
        ) from exc
    response = envelope(
        request,
        {
            "portfolio_fleet_run": serialize_portfolio_fleet_run(db, run),
            "created": created,
        },
    )
    if not created:
        response["meta"]["idempotent_replay"] = True
    return response


@router.get(
    "/organizations/{organization_id}/portfolio-fleet-runs/{run_id}"
)
def get_portfolio_fleet_run_detail(
    request: Request,
    organization_id: str,
    run_id: str,
    user: dict = Depends(portfolio_member),
    db: Session = Depends(get_db),
) -> dict:
    _enforce_scope(user, organization_id)
    try:
        _require_run_access(
            db,
            user=user,
            organization_id=organization_id,
            run_id=run_id,
            required_access_role="viewer",
        )
        run = get_portfolio_fleet_run(
            db,
            organization_id=organization_id,
            run_id=run_id,
        )
    except PortfolioFleetError as exc:
        _raise_fleet_error(exc)
    except PortfolioAccessError as exc:
        _raise_access_error(exc)
    return envelope(request, {"portfolio_fleet_run": serialize_portfolio_fleet_run(db, run)})


@router.post(
    "/organizations/{organization_id}/portfolio-fleet-runs/{run_id}/approve"
)
def post_portfolio_fleet_run_approval(
    request: Request,
    organization_id: str,
    run_id: str,
    body: PortfolioFleetRunDecisionIn,
    user: dict = Depends(portfolio_member),
    db: Session = Depends(get_db),
) -> dict:
    _enforce_scope(user, organization_id)
    try:
        _require_run_access(
            db,
            user=user,
            organization_id=organization_id,
            run_id=run_id,
            required_access_role="approver",
        )
        run = approve_portfolio_fleet_run(
            db,
            organization_id=organization_id,
            run_id=run_id,
            actor_user_id=user["id"],
            expected_version=body.expected_version,
        )
    except PortfolioFleetError as exc:
        db.rollback()
        _raise_fleet_error(exc)
    except PortfolioAccessError as exc:
        db.rollback()
        _raise_access_error(exc)
    return envelope(request, {"portfolio_fleet_run": serialize_portfolio_fleet_run(db, run)})


@router.post(
    "/organizations/{organization_id}/portfolio-fleet-runs/{run_id}/retry-failed"
)
def post_portfolio_fleet_run_retry(
    request: Request,
    organization_id: str,
    run_id: str,
    body: PortfolioFleetRunDecisionIn,
    user: dict = Depends(portfolio_member),
    db: Session = Depends(get_db),
) -> dict:
    _enforce_scope(user, organization_id)
    try:
        _require_run_access(
            db,
            user=user,
            organization_id=organization_id,
            run_id=run_id,
            required_access_role="operator",
        )
        run = retry_failed_portfolio_fleet_run_items(
            db,
            organization_id=organization_id,
            run_id=run_id,
            actor_user_id=user["id"],
            expected_version=body.expected_version,
        )
    except PortfolioFleetError as exc:
        db.rollback()
        _raise_fleet_error(exc)
    except PortfolioAccessError as exc:
        db.rollback()
        _raise_access_error(exc)
    return envelope(request, {"portfolio_fleet_run": serialize_portfolio_fleet_run(db, run)})


@router.post(
    "/organizations/{organization_id}/portfolio-fleet-runs/{run_id}/pause"
)
def post_portfolio_fleet_run_pause(
    request: Request,
    organization_id: str,
    run_id: str,
    body: PortfolioFleetRunDecisionIn,
    user: dict = Depends(portfolio_member),
    db: Session = Depends(get_db),
) -> dict:
    _enforce_scope(user, organization_id)
    try:
        _require_run_access(
            db,
            user=user,
            organization_id=organization_id,
            run_id=run_id,
            required_access_role="operator",
        )
        run = pause_portfolio_fleet_run(
            db,
            organization_id=organization_id,
            run_id=run_id,
            actor_user_id=user["id"],
            expected_version=body.expected_version,
        )
    except PortfolioFleetError as exc:
        db.rollback()
        _raise_fleet_error(exc)
    except PortfolioAccessError as exc:
        db.rollback()
        _raise_access_error(exc)
    return envelope(request, {"portfolio_fleet_run": serialize_portfolio_fleet_run(db, run)})


@router.post(
    "/organizations/{organization_id}/portfolio-fleet-runs/{run_id}/resume"
)
def post_portfolio_fleet_run_resume(
    request: Request,
    organization_id: str,
    run_id: str,
    body: PortfolioFleetRunDecisionIn,
    user: dict = Depends(portfolio_member),
    db: Session = Depends(get_db),
) -> dict:
    _enforce_scope(user, organization_id)
    try:
        _require_run_access(
            db,
            user=user,
            organization_id=organization_id,
            run_id=run_id,
            required_access_role="operator",
        )
        run = resume_portfolio_fleet_run(
            db,
            organization_id=organization_id,
            run_id=run_id,
            actor_user_id=user["id"],
            expected_version=body.expected_version,
        )
    except PortfolioFleetError as exc:
        db.rollback()
        _raise_fleet_error(exc)
    except PortfolioAccessError as exc:
        db.rollback()
        _raise_access_error(exc)
    return envelope(request, {"portfolio_fleet_run": serialize_portfolio_fleet_run(db, run)})


def _enforce_scope(user: dict, organization_id: str) -> None:
    enforce_organization_scope(
        user=user,
        organization_id=organization_id,
        allow_platform=False,
    )


def _accessible_group_ids(
    db: Session,
    *,
    user: dict,
    organization_id: str,
) -> set[str] | None:
    return accessible_location_group_ids(
        db,
        organization_id=organization_id,
        user_id=user["id"],
        org_role=str(user.get("org_role") or ""),
        required_access_role="viewer",
    )


def _require_snapshot_access(
    db: Session,
    *,
    user: dict,
    organization_id: str,
    target_snapshot_id: str,
    required_access_role: str,
) -> None:
    snapshot = (
        db.query(PortfolioTargetSnapshot)
        .filter(
            PortfolioTargetSnapshot.organization_id == organization_id,
            PortfolioTargetSnapshot.id == target_snapshot_id,
        )
        .first()
    )
    if snapshot is None:
        return
    require_location_group_access(
        db,
        organization_id=organization_id,
        user_id=user["id"],
        org_role=str(user.get("org_role") or ""),
        location_group_id=snapshot.location_group_id,
        required_access_role=required_access_role,
    )


def _require_run_access(
    db: Session,
    *,
    user: dict,
    organization_id: str,
    run_id: str,
    required_access_role: str,
) -> None:
    row = (
        db.query(PortfolioTargetSnapshot.location_group_id)
        .join(
            PortfolioFleetRun,
            PortfolioFleetRun.target_snapshot_id == PortfolioTargetSnapshot.id,
        )
        .filter(
            PortfolioFleetRun.organization_id == organization_id,
            PortfolioFleetRun.id == run_id,
            PortfolioTargetSnapshot.organization_id == organization_id,
        )
        .first()
    )
    if row is None:
        return
    require_location_group_access(
        db,
        organization_id=organization_id,
        user_id=user["id"],
        org_role=str(user.get("org_role") or ""),
        location_group_id=row[0],
        required_access_role=required_access_role,
    )


def _raise_access_error(exc: PortfolioAccessError) -> None:
    messages = {
        "portfolio_access_role_invalid": "Choose viewer, operator, or approver access.",
        "portfolio_access_grantee_required": "Enter the teammate's email address.",
        "portfolio_access_grantee_not_found": "That email is not an active teammate in this account.",
        "portfolio_access_admin_grant_not_needed": "Owners and administrators already have access to every location group.",
        "portfolio_access_group_not_found": "The saved location group was not found.",
        "portfolio_access_group_inactive": "Reactivate this location group before assigning it.",
        "portfolio_access_grant_not_found": "The delegated-access record was not found.",
        "portfolio_access_version_conflict": "This access record changed. Refresh before trying again.",
        "portfolio_access_upgrade_required": "Delegated location access is available on Growth and Enterprise plans.",
        "portfolio_access_group_required": "Choose one of your assigned location groups.",
        "portfolio_access_denied": "You are not assigned to this location group.",
        "portfolio_access_operator_required": "Operator access is required for this location group.",
        "portfolio_access_approval_required": "Approver access is required to start this work.",
        "portfolio_access_target_outside_group": "A selected location is outside your assigned group.",
        "organization_not_found": "The business account was not found.",
    }
    raise HTTPException(
        status_code=exc.status_code,
        detail={
            "message": messages.get(exc.reason_code, "This location-group action is not allowed."),
            "reason_code": exc.reason_code,
        },
    ) from exc


def _raise_targeting_error(exc: PortfolioTargetingError) -> None:
    messages = {
        "location_group_not_found": "Saved location group not found.",
        "location_group_version_conflict": "This group changed after you opened it. Refresh before saving again.",
        "location_group_name_conflict": "A group with this name already exists.",
        "location_group_not_active": "This saved group is archived.",
        "one_or_more_locations_unavailable": "One or more locations are not available in this account.",
        "explicit_target_selection_required": "Choose a saved group or select locations before continuing.",
        "ambiguous_target_selection": "Choose either a saved group or every active location, not both.",
        "region_filter_requires_base_selection": "Choose a saved group or every active location before filtering by area.",
        "location_cannot_be_included_and_excluded": "A location cannot be both included and excluded.",
        "target_request_key_conflict": "This target request was already used for a different list.",
    }
    raise HTTPException(
        status_code=exc.status_code,
        detail={
            "message": messages.get(exc.reason_code, "The target list could not be saved."),
            "reason_code": exc.reason_code,
        },
    ) from exc


def _raise_fleet_error(exc: PortfolioFleetError) -> None:
    messages = {
        "target_snapshot_not_found": "The saved target list was not found.",
        "fleet_action_not_supported": "This saved action is not available for bulk work yet.",
        "fleet_request_key_required": "A safe request key is required.",
        "fleet_request_key_conflict": "This request key was already used for a different target list.",
        "fleet_run_not_found": "The bulk-work run was not found.",
        "fleet_run_version_conflict": "This run changed after you opened it. Refresh before continuing.",
        "fleet_run_has_no_ready_locations": "No locations are ready to start. Fix the listed setup items first.",
        "fleet_run_not_awaiting_approval": "This run is not waiting for approval.",
        "fleet_run_not_running": "This run is not currently in progress.",
        "fleet_run_not_paused": "This run is not paused.",
        "fleet_run_has_no_waiting_locations": "There are no waiting locations to pause.",
        "fleet_target_snapshot_changed": "The approved target record no longer matches this run.",
        "fleet_run_has_no_failed_locations": "There are no failed locations to retry.",
        "fleet_run_retry_not_available": "The failed locations cannot be retried from this run.",
        "fleet_feature_upgrade_required": "Bulk location work is available on Growth and Enterprise plans.",
        "fleet_credit_allowance_exhausted": "This work needs more Insight Credits than the account has available.",
        "organization_not_found": "The business account was not found.",
    }
    raise HTTPException(
        status_code=exc.status_code,
        detail={
            "message": messages.get(exc.reason_code, "The bulk-work run could not be updated."),
            "reason_code": exc.reason_code,
        },
    ) from exc
