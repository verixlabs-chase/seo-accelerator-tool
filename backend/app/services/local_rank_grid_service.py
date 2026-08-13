from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
import json
import math
import re
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.models.business_location import BusinessLocation
from app.models.campaign import Campaign
from app.models.competitor import Competitor
from app.models.cost_economics import CostLedgerEntry
from app.models.local_rank_grid import (
    LocalRankGridCompetitorPoint,
    LocalRankGridPoint,
    LocalRankGridRun,
)
from app.models.organization import Organization
from app.models.rank import CampaignKeyword
from app.providers.local_rank_grid import GridTaskRequest, build_provider, normalize_domain
from app.services import job_service, metric_contract_service
from app.services.cost_economics_service import (
    calculate_provider_cost,
    get_customer_credit_summary,
    reconcile_provider_cost,
    release_provider_cost,
    reserve_provider_cost,
    resolve_plan_economics,
)
from app.services.provider_credentials_service import (
    ProviderCredentialConfigurationError,
    resolve_provider_credential_owner,
    resolve_provider_credentials,
)


PROVIDER_NAME = "dataforseo"
CAPABILITY = "local_rank_grid"
OPERATION = "google_maps_standard"
JOB_TYPE = "local.rank_grid.dispatch"
TERMINAL_POINT_STATUSES = {"ranked", "not_found", "failed"}
PLAN_LIMITS = {
    "solo": {"grid": 5, "keywords": 2, "daily_runs": 5, "competitors": 3},
    "multi_location": {"grid": 7, "keywords": 3, "daily_runs": 20, "competitors": 10},
    "enterprise": {"grid": 7, "keywords": 3, "daily_runs": 100, "competitors": 25},
}


class LocalRankGridError(RuntimeError):
    def __init__(self, message: str, *, reason_code: str, status_code: int = 409) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.status_code = status_code


def _campaign_context(
    db: Session, *, tenant_id: str, organization_id: str, campaign_id: str
) -> tuple[Campaign, BusinessLocation, Organization]:
    campaign = (
        db.query(Campaign)
        .filter(
            Campaign.id == campaign_id,
            Campaign.tenant_id == tenant_id,
            Campaign.organization_id == organization_id,
        )
        .first()
    )
    if campaign is None or campaign.setup_state.lower() != "active":
        raise LocalRankGridError(
            "Choose an active business location first.",
            reason_code="active_campaign_required",
            status_code=404,
        )
    location = db.get(BusinessLocation, campaign.business_location_id)
    if (
        location is None
        or location.organization_id != organization_id
        or location.status.lower() != "active"
    ):
        raise LocalRankGridError(
            "This business location is not active.",
            reason_code="active_location_required",
            status_code=409,
        )
    if location.latitude is None or location.longitude is None:
        raise LocalRankGridError(
            "Place this business on the map before running an area search check.",
            reason_code="location_coordinates_required",
        )
    if not location.provider_location_code or not location.provider_location_name:
        raise LocalRankGridError(
            "Finish the search-area setup before running an area search check.",
            reason_code="search_area_required",
        )
    organization = db.get(Organization, organization_id)
    if organization is None or organization.status.lower() != "active":
        raise LocalRankGridError(
            "This account is not active.", reason_code="active_organization_required"
        )
    return campaign, location, organization


def _selected_keywords(
    db: Session, *, tenant_id: str, campaign_id: str, keyword_ids: list[str]
) -> list[CampaignKeyword]:
    rows = (
        db.query(CampaignKeyword)
        .filter(
            CampaignKeyword.tenant_id == tenant_id,
            CampaignKeyword.campaign_id == campaign_id,
            CampaignKeyword.id.in_(keyword_ids),
        )
        .all()
    )
    rows_by_id = {row.id: row for row in rows}
    ordered = [rows_by_id[item_id] for item_id in keyword_ids if item_id in rows_by_id]
    if len(ordered) != len(keyword_ids):
        raise LocalRankGridError(
            "One or more selected search phrases do not belong to this location.",
            reason_code="keyword_selection_invalid",
            status_code=400,
        )
    return ordered


def _limits(organization: Organization) -> dict[str, int]:
    code = resolve_plan_economics(organization.plan_type).code
    return PLAN_LIMITS[code]


def _validate_limits(
    *, organization: Organization, keyword_count: int, grid_size: int, radius_miles: float
) -> dict[str, int]:
    limits = _limits(organization)
    if grid_size not in {3, 5, 7} or grid_size > limits["grid"]:
        raise LocalRankGridError(
            f"This plan supports an area grid up to {limits['grid']} by {limits['grid']}.",
            reason_code="grid_size_not_in_plan",
            status_code=403,
        )
    if keyword_count > limits["keywords"]:
        raise LocalRankGridError(
            f"Choose no more than {limits['keywords']} search phrases for this check.",
            reason_code="keyword_count_not_in_plan",
            status_code=403,
        )
    if radius_miles < 1 or radius_miles > 25:
        raise LocalRankGridError(
            "Choose an area between 1 and 25 miles.",
            reason_code="radius_invalid",
            status_code=400,
        )
    return limits


def _credential_owner(db: Session, organization_id: str) -> str:
    try:
        return resolve_provider_credential_owner(db, organization_id, PROVIDER_NAME)
    except ProviderCredentialConfigurationError as exc:
        raise LocalRankGridError(
            "Connect the search data account before running an area search check.",
            reason_code=exc.reason_code,
            status_code=exc.status_code,
        ) from exc


def _confirmed_competitor_snapshot(
    db: Session, *, tenant_id: str, campaign_id: str, limit: int
) -> list[dict[str, str | None]]:
    rows = (
        db.query(Competitor)
        .filter(
            Competitor.tenant_id == tenant_id,
            Competitor.campaign_id == campaign_id,
            Competitor.review_status == "confirmed",
        )
        .order_by(Competitor.created_at.asc(), Competitor.id.asc())
        .limit(max(0, limit))
        .all()
    )
    return [
        {"id": row.id, "domain": normalize_domain(row.domain), "label": row.label}
        for row in rows
        if normalize_domain(row.domain)
    ]


def preview_run(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
    keyword_ids: list[str],
    grid_size: int,
    radius_miles: float,
) -> dict[str, Any]:
    _campaign, location, organization = _campaign_context(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
    )
    keywords = _selected_keywords(
        db, tenant_id=tenant_id, campaign_id=campaign_id, keyword_ids=keyword_ids
    )
    limits = _validate_limits(
        organization=organization,
        keyword_count=len(keywords),
        grid_size=grid_size,
        radius_miles=radius_miles,
    )
    owner = _credential_owner(db, organization_id)
    total_checks = grid_size * grid_size * len(keywords)
    cost = calculate_provider_cost(
        db,
        provider_name=PROVIDER_NAME,
        capability=CAPABILITY,
        operation=OPERATION,
        quantity=total_checks,
    )
    credit_summary = get_customer_credit_summary(db, organization_id=organization_id)
    estimated_credits = (
        int((cost / Decimal("0.01")).to_integral_value(rounding="ROUND_CEILING"))
        if owner == "platform"
        else 0
    )
    remaining = int(credit_summary["credits"]["remaining"])
    competitor_snapshot = _confirmed_competitor_snapshot(
        db,
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        limit=limits["competitors"],
    )
    return {
        "campaign_id": campaign_id,
        "business_location_id": location.id,
        "location_name": location.name,
        "keywords": [{"id": row.id, "keyword": row.keyword} for row in keywords],
        "grid_size": grid_size,
        "radius_miles": float(radius_miles),
        "points_per_phrase": grid_size * grid_size,
        "total_checks": total_checks,
        "estimated_credits": estimated_credits,
        "credits_remaining": remaining,
        "credits_after": max(0, remaining - estimated_credits),
        "connected_account": owner == "organization",
        "completion_mode": "standard_queue",
        "completion_message": "Usually ready in several minutes; some checks can take longer.",
        "source_label": "Google Maps results",
        "competitors_included": competitor_snapshot,
        "competitor_limit": limits["competitors"],
        "limits": limits,
        "can_start": owner == "organization" or estimated_credits <= remaining,
    }


def _grid_points(latitude: float, longitude: float, grid_size: int, radius_miles: float):
    center = (grid_size - 1) / 2
    latitude_step = (radius_miles / 69.0) / max(1, center)
    longitude_scale = max(0.2, math.cos(math.radians(latitude)))
    longitude_step = (radius_miles / (69.0 * longitude_scale)) / max(1, center)
    for row_index in range(grid_size):
        for column_index in range(grid_size):
            yield (
                row_index * grid_size + column_index,
                row_index,
                column_index,
                latitude + ((center - row_index) * latitude_step),
                longitude + ((column_index - center) * longitude_step),
            )


def create_run(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    created_by_user_id: str | None,
    campaign_id: str,
    keyword_ids: list[str],
    grid_size: int,
    radius_miles: float,
    idempotency_key: str,
) -> tuple[LocalRankGridRun, bool]:
    existing = (
        db.query(LocalRankGridRun)
        .filter(
            LocalRankGridRun.organization_id == organization_id,
            LocalRankGridRun.idempotency_key == idempotency_key,
        )
        .first()
    )
    if existing is not None:
        return existing, False

    preview = preview_run(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
        keyword_ids=keyword_ids,
        grid_size=grid_size,
        radius_miles=radius_miles,
    )
    campaign, location, organization = _campaign_context(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
    )
    limits = _limits(organization)
    today = datetime.now(UTC).date()
    daily_runs = (
        db.query(LocalRankGridRun)
        .filter(
            LocalRankGridRun.organization_id == organization_id,
            LocalRankGridRun.created_at >= datetime.combine(today, datetime.min.time(), tzinfo=UTC),
        )
        .count()
    )
    if daily_runs >= limits["daily_runs"]:
        raise LocalRankGridError(
            "This account has reached its area-check safety limit for today.",
            reason_code="daily_rank_grid_limit_reached",
            status_code=429,
        )
    owner = "organization" if preview["connected_account"] else "platform"
    reservation = reserve_provider_cost(
        db,
        organization_id=organization_id,
        provider_name=PROVIDER_NAME,
        capability=CAPABILITY,
        operation=OPERATION,
        credential_owner=owner,
        quantity=preview["total_checks"],
        idempotency_key=f"local-rank-grid:{idempotency_key}",
        business_location_id=location.id,
        campaign_id=campaign.id,
    )
    now = datetime.now(UTC)
    language_code = get_settings().local_rank_grid_language_code or "en"
    device_class = "provider_default"
    configured_backend = (
        get_settings().local_rank_grid_provider_backend.strip().lower()
        or get_settings().rank_provider_backend.strip().lower()
        or "configured_provider"
    )
    provider_method = f"{configured_backend}:google_maps_standard"
    grid_definition = {
        "grid_size": grid_size,
        "radius_miles": float(radius_miles),
        "center_latitude": round(float(location.latitude), 7),
        "center_longitude": round(float(location.longitude), 7),
        "provider_location_code": str(location.provider_location_code),
        "language_code": language_code,
        "device_class": device_class,
        "provider_method": provider_method,
    }
    grid_definition_hash = sha256(
        json.dumps(grid_definition, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    run = LocalRankGridRun(
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign.id,
        business_location_id=location.id,
        idempotency_key=idempotency_key,
        status="queued",
        grid_size=grid_size,
        radius_miles=Decimal(str(radius_miles)),
        center_latitude=Decimal(str(location.latitude)),
        center_longitude=Decimal(str(location.longitude)),
        provider_location_code=str(location.provider_location_code),
        provider_location_name=str(location.provider_location_name),
        provider_location_type=location.provider_location_type,
        keyword_snapshot=preview["keywords"],
        competitor_snapshot=preview["competitors_included"],
        keyword_count=len(keyword_ids),
        total_checks=preview["total_checks"],
        completion_mode="standard_queue",
        credential_owner=owner,
        reservation_id=reservation.id,
        estimated_cost=Decimal(reservation.estimated_cost),
        estimated_credit_units=int(reservation.customer_credit_units or 0),
        target_business_name=location.name,
        target_domain=location.domain or campaign.domain,
        source_name="google_maps_results",
        metric_contract_id="local_grid.position",
        metric_contract_version=metric_contract_service.contract_definition(
            "local_grid.position", db=db
        ).version,
        grid_definition_hash=grid_definition_hash,
        language_code=language_code,
        device_class=device_class,
        provider_method=provider_method,
        created_by_user_id=created_by_user_id,
        created_at=now,
        updated_at=now,
    )
    db.add(run)
    db.flush()
    keywords = _selected_keywords(
        db, tenant_id=tenant_id, campaign_id=campaign_id, keyword_ids=keyword_ids
    )
    for keyword in keywords:
        point_scope = metric_contract_service.scope_evidence(
            "local_grid.position",
            {
                "organization_id": organization_id,
                "campaign_id": campaign.id,
                "business_location_id": location.id,
                "keyword_id": keyword.id,
                "grid_definition_hash": grid_definition_hash,
                "language_code": language_code,
                "device_class": device_class,
                "provider_method": provider_method,
                "run_timestamp": now,
                **grid_definition,
            },
            db=db,
        )
        for index, row, column, latitude, longitude in _grid_points(
            float(location.latitude), float(location.longitude), grid_size, radius_miles
        ):
            db.add(
                LocalRankGridPoint(
                    run_id=run.id,
                    tenant_id=tenant_id,
                    organization_id=organization_id,
                    campaign_id=campaign.id,
                    business_location_id=location.id,
                    keyword_id=keyword.id,
                    keyword=keyword.keyword,
                    grid_index=index,
                    row_index=row,
                    column_index=column,
                    latitude=Decimal(str(round(latitude, 7))),
                    longitude=Decimal(str(round(longitude, 7))),
                    status="queued",
                    source_name="google_maps_results",
                    metric_contract_id="local_grid.position",
                    metric_contract_version=point_scope["metric_contract_version"],
                    scope_key=point_scope["scope_key"],
                    created_at=now,
                    updated_at=now,
                )
            )
    job_service.create_job(
        db,
        tenant_id=tenant_id,
        job_type=JOB_TYPE,
        entity_type="local_rank_grid_run",
        entity_id=run.id,
        idempotency_key=f"local-rank-grid-dispatch:{run.id}",
        payload={"tenant_id": tenant_id, "organization_id": organization_id, "run_id": run.id},
        max_retries=2,
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        concurrent = (
            db.query(LocalRankGridRun)
            .filter(
                LocalRankGridRun.organization_id == organization_id,
                LocalRankGridRun.idempotency_key == idempotency_key,
            )
            .first()
        )
        if concurrent is not None:
            return concurrent, False
        release_provider_cost(db, reservation=reservation)
        raise
    db.refresh(run)
    return run, True


def _provider_for_run(db: Session, run: LocalRankGridRun):
    settings = get_settings()
    backend = (
        settings.local_rank_grid_provider_backend.strip().lower()
        or settings.rank_provider_backend.strip().lower()
    )
    credentials = (
        {}
        if backend == "synthetic"
        else resolve_provider_credentials(db, run.organization_id, PROVIDER_NAME)
    )
    return build_provider(backend=backend, credentials=credentials)


def dispatch_run(db: Session, *, run_id: str, tenant_id: str) -> dict[str, Any]:
    run = db.get(LocalRankGridRun, run_id)
    if run is None or run.tenant_id != tenant_id:
        raise ValueError("Area search run was not found.")
    queued = (
        db.query(LocalRankGridPoint)
        .filter(LocalRankGridPoint.run_id == run.id, LocalRankGridPoint.status == "queued")
        .order_by(LocalRankGridPoint.keyword_id, LocalRankGridPoint.grid_index)
        .all()
    )
    if not queued:
        return {"run_id": run.id, "submitted": 0, "status": run.status}
    provider = _provider_for_run(db, run)
    run.status = "submitting"
    run.error_code = None
    run.error_message = None
    db.commit()
    submitted = 0
    try:
        for offset in range(0, len(queued), 100):
            batch = queued[offset : offset + 100]
            results = provider.submit(
                [
                    GridTaskRequest(
                        point_id=point.id,
                        keyword=point.keyword,
                        latitude=float(point.latitude),
                        longitude=float(point.longitude),
                        tag=f"rank-grid:{run.id}:{point.id}",
                    )
                    for point in batch
                ]
            )
            by_point = {str(item.get("point_id")): item for item in results}
            for point in batch:
                result = by_point.get(point.id, {})
                point.provider_task_id = result.get("task_id")
                point.provider_status_code = result.get("status_code")
                point.provider_status_message = result.get("status_message")
                point.provider_reported_cost = Decimal(str(result.get("cost") or "0"))
                point.status = str(result.get("status") or "failed")
                point.rank = result.get("rank")
                point.matched_business_name = result.get("matched_business_name")
                point.matched_business_domain = result.get("matched_business_domain")
                if point.status in {"ranked", "not_found"}:
                    point.captured_at = datetime.now(UTC)
                point.updated_at = datetime.now(UTC)
                submitted += int(point.status != "failed")
            db.commit()
    except Exception as exc:
        for point in queued:
            if point.status == "queued":
                point.status = "failed"
                point.provider_reported_cost = Decimal("0")
                point.provider_status_message = "This check could not be submitted."
        run.error_code = "provider_submission_failed"
        run.error_message = str(exc)[:1000]
        db.commit()
    run.submitted_at = run.submitted_at or datetime.now(UTC)
    _refresh_run_totals(db, run)
    db.commit()
    return {"run_id": run.id, "submitted": submitted, "status": run.status}


def _normalized_name(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def _target_match(run: LocalRankGridRun, items: list[dict[str, Any]]) -> dict[str, Any] | None:
    target_domain = normalize_domain(run.target_domain)
    target_name = _normalized_name(run.target_business_name)
    for item in items:
        if not isinstance(item, dict) or str(item.get("type") or "") != "maps_search":
            continue
        row_domain = normalize_domain(
            str(item.get("domain") or item.get("url") or item.get("website") or "")
        )
        row_name = _normalized_name(str(item.get("title") or item.get("name") or ""))
        domain_match = bool(
            target_domain
            and row_domain
            and (row_domain == target_domain or row_domain.endswith(f".{target_domain}"))
        )
        name_match = bool(
            target_name and row_name and (target_name == row_name or target_name in row_name)
        )
        if domain_match or name_match:
            return {
                "rank": int(item.get("rank_absolute") or item.get("rank_group") or 0),
                "name": str(item.get("title") or item.get("name") or "") or None,
                "domain": row_domain or None,
            }
    return None


def _competitor_match(competitor_domain: str, items: list[dict[str, Any]]) -> dict[str, Any] | None:
    target_domain = normalize_domain(competitor_domain)
    if not target_domain:
        return None
    for item in items:
        if not isinstance(item, dict) or str(item.get("type") or "") != "maps_search":
            continue
        row_domain = normalize_domain(
            str(item.get("domain") or item.get("url") or item.get("website") or "")
        )
        if not row_domain or not (
            row_domain == target_domain or row_domain.endswith(f".{target_domain}")
        ):
            continue
        rank = int(item.get("rank_absolute") or item.get("rank_group") or 0)
        if rank <= 0:
            return None
        return {
            "rank": rank,
            "name": str(item.get("title") or item.get("name") or "") or None,
            "domain": row_domain,
        }
    return None


def _save_competitor_points(
    db: Session,
    *,
    run: LocalRankGridRun,
    point: LocalRankGridPoint,
    items: list[dict[str, Any]],
    captured_at: datetime,
) -> None:
    competitors = [row for row in (run.competitor_snapshot or []) if isinstance(row, dict)]
    if not competitors:
        return
    existing = {
        row.competitor_id: row
        for row in db.query(LocalRankGridCompetitorPoint)
        .filter(LocalRankGridCompetitorPoint.point_id == point.id)
        .all()
    }
    for competitor in competitors:
        competitor_id = str(competitor.get("id") or "").strip()
        competitor_domain = normalize_domain(str(competitor.get("domain") or ""))
        if not competitor_id or not competitor_domain:
            continue
        match = _competitor_match(competitor_domain, items)
        row = existing.get(competitor_id)
        if row is None:
            row = LocalRankGridCompetitorPoint(
                run_id=run.id,
                point_id=point.id,
                tenant_id=run.tenant_id,
                organization_id=run.organization_id,
                campaign_id=run.campaign_id,
                business_location_id=run.business_location_id,
                competitor_id=competitor_id,
                competitor_domain=competitor_domain,
                competitor_label=str(competitor.get("label") or "").strip() or None,
                keyword_id=point.keyword_id,
                keyword=point.keyword,
                grid_index=point.grid_index,
                status="ranked" if match else "not_found",
                rank=match["rank"] if match else None,
                matched_business_name=match["name"] if match else None,
                matched_business_domain=match["domain"] if match else None,
                captured_at=captured_at,
                created_at=captured_at,
            )
            db.add(row)
        else:
            row.status = "ranked" if match else "not_found"
            row.rank = match["rank"] if match else None
            row.matched_business_name = match["name"] if match else None
            row.matched_business_domain = match["domain"] if match else None
            row.captured_at = captured_at


def refresh_run(
    db: Session, *, tenant_id: str, organization_id: str, run_id: str
) -> LocalRankGridRun:
    run = (
        db.query(LocalRankGridRun)
        .filter(
            LocalRankGridRun.id == run_id,
            LocalRankGridRun.tenant_id == tenant_id,
            LocalRankGridRun.organization_id == organization_id,
        )
        .first()
    )
    if run is None:
        raise LocalRankGridError(
            "Area search run not found.", reason_code="run_not_found", status_code=404
        )
    pending = (
        db.query(LocalRankGridPoint)
        .filter(LocalRankGridPoint.run_id == run.id, LocalRankGridPoint.status == "pending")
        .all()
    )
    if not pending:
        _refresh_run_totals(db, run)
        db.commit()
        return run
    provider = _provider_for_run(db, run)
    for point in pending:
        result = provider.fetch(str(point.provider_task_id))
        point.provider_status_code = result.get("status_code")
        point.provider_status_message = result.get("status_message")
        point.provider_reported_cost = Decimal(
            str(result.get("cost") or point.provider_reported_cost or "0")
        )
        if result.get("status") == "failed":
            point.status = "failed"
            point.provider_reported_cost = Decimal("0")
        elif result.get("status") == "ready":
            result_items = result.get("items") or []
            captured_at = datetime.now(UTC)
            match = _target_match(run, result_items)
            if match and match["rank"] > 0:
                point.status = "ranked"
                point.rank = match["rank"]
                point.matched_business_name = match["name"]
                point.matched_business_domain = match["domain"]
            else:
                point.status = "not_found"
                point.rank = None
            point.captured_at = captured_at
            _save_competitor_points(
                db,
                run=run,
                point=point,
                items=result_items,
                captured_at=captured_at,
            )
        point.updated_at = datetime.now(UTC)
    _refresh_run_totals(db, run)
    db.commit()
    db.refresh(run)
    return run


def _refresh_run_totals(db: Session, run: LocalRankGridRun) -> None:
    points = db.query(LocalRankGridPoint).filter(LocalRankGridPoint.run_id == run.id).all()
    run.completed_checks = sum(point.status in TERMINAL_POINT_STATUSES for point in points)
    run.failed_checks = sum(point.status == "failed" for point in points)
    run.not_found_checks = sum(point.status == "not_found" for point in points)
    pending = sum(point.status in {"queued", "pending"} for point in points)
    if pending:
        run.status = "partial" if run.completed_checks else "pending"
    else:
        run.status = "failed" if run.failed_checks == run.total_checks else "completed"
        run.completed_at = datetime.now(UTC)
        if run.reservation_id:
            reservation = db.get(CostLedgerEntry, run.reservation_id)
            if reservation is not None:
                actual = sum(
                    (
                        Decimal(point.provider_reported_cost or 0)
                        for point in points
                        if point.status != "failed"
                    ),
                    Decimal("0"),
                )
                if run.status == "failed":
                    release_provider_cost(db, reservation=reservation)
                else:
                    reconcile_provider_cost(
                        db, reservation=reservation, provider_reported_cost=actual
                    )
                run.provider_reported_cost = actual
    run.updated_at = datetime.now(UTC)


def get_run(db: Session, *, tenant_id: str, organization_id: str, run_id: str) -> LocalRankGridRun:
    row = (
        db.query(LocalRankGridRun)
        .filter(
            LocalRankGridRun.id == run_id,
            LocalRankGridRun.tenant_id == tenant_id,
            LocalRankGridRun.organization_id == organization_id,
        )
        .first()
    )
    if row is None:
        raise LocalRankGridError(
            "Area search run not found.", reason_code="run_not_found", status_code=404
        )
    return row


def list_runs(
    db: Session, *, tenant_id: str, organization_id: str, campaign_id: str, limit: int = 12
) -> list[LocalRankGridRun]:
    return (
        db.query(LocalRankGridRun)
        .filter(
            LocalRankGridRun.tenant_id == tenant_id,
            LocalRankGridRun.organization_id == organization_id,
            LocalRankGridRun.campaign_id == campaign_id,
        )
        .order_by(LocalRankGridRun.created_at.desc())
        .limit(max(1, min(limit, 50)))
        .all()
    )


def serialize_run(
    db: Session, run: LocalRankGridRun, *, include_points: bool = True
) -> dict[str, Any]:
    points: list[dict[str, Any]] = []
    competitor_points: list[dict[str, Any]] = []
    rows: list[LocalRankGridPoint] = []
    competitor_rows: list[LocalRankGridCompetitorPoint] = []
    if include_points:
        rows = (
            db.query(LocalRankGridPoint)
            .filter(LocalRankGridPoint.run_id == run.id)
            .order_by(LocalRankGridPoint.keyword_id, LocalRankGridPoint.grid_index)
            .all()
        )
        points = [
            {
                "id": row.id,
                "keyword_id": row.keyword_id,
                "keyword": row.keyword,
                "grid_index": row.grid_index,
                "row_index": row.row_index,
                "column_index": row.column_index,
                "latitude": float(row.latitude),
                "longitude": float(row.longitude),
                "status": row.status,
                "rank": row.rank,
                "matched_business_name": row.matched_business_name,
                "source_label": "Google Maps results",
                "captured_at": row.captured_at.isoformat() if row.captured_at else None,
                "metric_contract": {
                    "id": row.metric_contract_id,
                    "version": row.metric_contract_version,
                    "scope_key": row.scope_key,
                },
            }
            for row in rows
        ]
        competitor_rows = (
            db.query(LocalRankGridCompetitorPoint)
            .filter(LocalRankGridCompetitorPoint.run_id == run.id)
            .order_by(
                LocalRankGridCompetitorPoint.keyword_id,
                LocalRankGridCompetitorPoint.competitor_id,
                LocalRankGridCompetitorPoint.grid_index,
            )
            .all()
        )
        competitor_points = [
            {
                "id": row.id,
                "point_id": row.point_id,
                "competitor_id": row.competitor_id,
                "competitor_domain": row.competitor_domain,
                "competitor_label": row.competitor_label,
                "keyword_id": row.keyword_id,
                "keyword": row.keyword,
                "grid_index": row.grid_index,
                "status": row.status,
                "rank": row.rank,
                "matched_business_name": row.matched_business_name,
                "captured_at": row.captured_at.isoformat(),
            }
            for row in competitor_rows
        ]
    return {
        "id": run.id,
        "campaign_id": run.campaign_id,
        "business_location_id": run.business_location_id,
        "status": run.status,
        "grid_size": run.grid_size,
        "radius_miles": float(run.radius_miles),
        "center": {
            "latitude": float(run.center_latitude),
            "longitude": float(run.center_longitude),
        },
        "keywords": list(run.keyword_snapshot or []),
        "competitors": list(run.competitor_snapshot or []),
        "keyword_count": run.keyword_count,
        "total_checks": run.total_checks,
        "completed_checks": run.completed_checks,
        "failed_checks": run.failed_checks,
        "not_found_checks": run.not_found_checks,
        "estimated_credits": run.estimated_credit_units,
        "completion_mode": run.completion_mode,
        "source_label": "Google Maps results",
        "measurement_contract": {
            "id": run.metric_contract_id,
            "version": run.metric_contract_version,
            "grid_definition_hash": run.grid_definition_hash,
            "language_code": run.language_code,
            "device_class": run.device_class,
            "provider_method": run.provider_method,
        },
        "visibility_summary": _grid_summary(db, run, rows) if rows else [],
        "competitor_overlap_summary": _competitor_overlap_summary(
            run=run,
            owner_rows=rows,
            competitor_rows=competitor_rows,
        ),
        "error_message": ("Some map checks could not be completed." if run.error_message else None),
        "created_at": run.created_at.isoformat(),
        "submitted_at": run.submitted_at.isoformat() if run.submitted_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "points": points,
        "competitor_points": competitor_points,
    }


def _competitor_overlap_summary(
    *,
    run: LocalRankGridRun,
    owner_rows: list[LocalRankGridPoint],
    competitor_rows: list[LocalRankGridCompetitorPoint],
) -> list[dict[str, Any]]:
    owner_by_scope = {(row.keyword_id, row.grid_index): row for row in owner_rows}
    grouped: dict[tuple[str, str], list[LocalRankGridCompetitorPoint]] = {}
    for row in competitor_rows:
        grouped.setdefault((row.keyword_id, row.competitor_id), []).append(row)
    snapshots = {
        str(item.get("id")): item
        for item in (run.competitor_snapshot or [])
        if isinstance(item, dict) and item.get("id")
    }
    summaries: list[dict[str, Any]] = []
    for (keyword_id, competitor_id), rows in sorted(grouped.items()):
        owner_ahead = 0
        competitor_ahead = 0
        tied = 0
        comparable = 0
        competitor_found = 0
        for competitor_row in rows:
            owner = owner_by_scope.get((keyword_id, competitor_row.grid_index))
            if owner is None or owner.status not in {"ranked", "not_found"}:
                continue
            comparable += 1
            owner_rank = owner.rank
            competitor_rank = competitor_row.rank
            competitor_found += int(competitor_rank is not None)
            if owner_rank is not None and (competitor_rank is None or owner_rank < competitor_rank):
                owner_ahead += 1
            elif competitor_rank is not None and (
                owner_rank is None or competitor_rank < owner_rank
            ):
                competitor_ahead += 1
            elif owner_rank is not None and competitor_rank is not None:
                tied += 1
        snapshot = snapshots.get(competitor_id, {})
        summaries.append(
            {
                "keyword_id": keyword_id,
                "keyword": rows[0].keyword,
                "competitor_id": competitor_id,
                "competitor_domain": rows[0].competitor_domain,
                "competitor_label": rows[0].competitor_label or snapshot.get("label"),
                "comparable_points": comparable,
                "owner_ahead": owner_ahead,
                "competitor_ahead": competitor_ahead,
                "tied": tied,
                "competitor_found": competitor_found,
            }
        )
    return summaries


def _grid_summary(
    db: Session,
    run: LocalRankGridRun,
    rows: list[LocalRankGridPoint],
) -> list[dict[str, Any]]:
    by_keyword: dict[str, list[LocalRankGridPoint]] = {}
    for row in rows:
        if row.status not in {"ranked", "not_found"}:
            continue
        by_keyword.setdefault(row.keyword_id, []).append(row)
    summaries: list[dict[str, Any]] = []
    for keyword_id, keyword_rows in sorted(by_keyword.items()):
        valid_count = len(keyword_rows)
        ranked = [row for row in keyword_rows if row.rank is not None]
        ranks = sorted(int(row.rank) for row in ranked if row.rank is not None)
        top_3 = sum(rank <= 3 for rank in ranks)
        top_10 = sum(rank <= 10 for rank in ranks)
        median_position = None
        if ranks:
            middle = len(ranks) // 2
            median_position = (
                float(ranks[middle])
                if len(ranks) % 2
                else (float(ranks[middle - 1]) + float(ranks[middle])) / 2.0
            )
        ranking_radius = max(
            (
                _distance_miles(
                    float(run.center_latitude),
                    float(run.center_longitude),
                    float(row.latitude),
                    float(row.longitude),
                )
                for row in ranked
                if row.rank is not None and int(row.rank) <= 10
            ),
            default=None,
        )
        summaries.append(
            {
                "keyword_id": keyword_id,
                "keyword": keyword_rows[0].keyword,
                "valid_points": valid_count,
                "top_3_share": round(top_3 / valid_count, 4) if valid_count else None,
                "top_10_share": round(top_10 / valid_count, 4) if valid_count else None,
                "median_position": median_position,
                "unranked_share": round((valid_count - len(ranks)) / valid_count, 4)
                if valid_count
                else None,
                "ranking_radius_miles": round(ranking_radius, 2)
                if ranking_radius is not None
                else None,
                "contract_versions": metric_contract_service.contract_versions(
                    (
                        "local_grid.top_3_share",
                        "local_grid.top_10_share",
                        "local_grid.median_position",
                        "local_grid.unranked_share",
                        "local_grid.ranking_radius",
                    ),
                    db=db,
                ),
            }
        )
    return summaries


def _distance_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_radius_miles = 3958.8
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return earth_radius_miles * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
