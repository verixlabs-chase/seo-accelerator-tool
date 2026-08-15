from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, ROUND_CEILING
import re
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.authority import DirectoryListingDiscoveryRun
from app.models.business_location import BusinessLocation
from app.models.campaign import Campaign
from app.models.cost_economics import CostLedgerEntry
from app.models.organization import Organization
from app.providers.listings import DataForSeoBusinessListingsProvider
from app.services import job_service, listing_inventory_service
from app.services.cost_economics_service import (
    CostEconomicsError,
    authorize_reserved_provider_dispatch,
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
CAPABILITY = "directory_listing_discovery"
OPERATION = "business_listings_live_limit_20"
JOB_TYPE = "directory_listings.discover"
RADIUS_KM = Decimal("25")
RESULT_LIMIT = 20
PLAN_DAILY_LIMITS = {"solo": 3, "multi_location": 20, "enterprise": 100}


class ListingDiscoveryError(RuntimeError):
    def __init__(self, message: str, *, reason_code: str, status_code: int = 409) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.status_code = status_code


def _context(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
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
        raise ListingDiscoveryError(
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
        raise ListingDiscoveryError(
            "This business location is not active.",
            reason_code="active_location_required",
        )
    if location.latitude is None or location.longitude is None:
        raise ListingDiscoveryError(
            "Add this business location to the map before checking its public listings.",
            reason_code="location_coordinates_required",
        )
    organization = db.get(Organization, organization_id)
    if organization is None or organization.status.lower() != "active":
        raise ListingDiscoveryError(
            "This account is not active.",
            reason_code="active_organization_required",
        )
    return campaign, location, organization


def _credential_owner(db: Session, organization_id: str) -> str:
    try:
        return resolve_provider_credential_owner(db, organization_id, PROVIDER_NAME)
    except ProviderCredentialConfigurationError as exc:
        raise ListingDiscoveryError(
            "Connect the search data account before checking public listings.",
            reason_code=exc.reason_code,
            status_code=exc.status_code,
        ) from exc


def preview_run(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
) -> dict[str, Any]:
    _campaign, location, organization = _context(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
    )
    owner = _credential_owner(db, organization_id)
    estimated_cost = calculate_provider_cost(
        db,
        provider_name=PROVIDER_NAME,
        capability=CAPABILITY,
        operation=OPERATION,
        quantity=1,
    )
    credit_summary = get_customer_credit_summary(db, organization_id=organization_id)
    estimated_credits = (
        int((estimated_cost / Decimal("0.01")).to_integral_value(rounding=ROUND_CEILING))
        if owner == "platform"
        else 0
    )
    remaining = int(credit_summary["credits"]["remaining"])
    plan_code = resolve_plan_economics(organization.plan_type).code
    return {
        "campaign_id": campaign_id,
        "business_location_id": location.id,
        "location_name": location.name,
        "estimated_credits": estimated_credits,
        "credits_remaining": remaining,
        "credits_after": max(0, remaining - estimated_credits),
        "connected_account": owner == "organization",
        "can_start": owner == "organization" or estimated_credits <= remaining,
        "daily_limit": PLAN_DAILY_LIMITS[plan_code],
        "scope": "supported_public_sources",
        "correction_available": False,
        "message": "This checks supported public listing sources for the selected location.",
    }


def create_run(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
    requested_by_user_id: str | None,
    idempotency_key: str,
) -> tuple[DirectoryListingDiscoveryRun, bool]:
    clean_key = idempotency_key.strip()
    if not clean_key or len(clean_key) > 160:
        raise ListingDiscoveryError(
            "The listing check request is invalid.",
            reason_code="idempotency_key_invalid",
            status_code=400,
        )
    existing = (
        db.query(DirectoryListingDiscoveryRun)
        .filter(
            DirectoryListingDiscoveryRun.organization_id == organization_id,
            DirectoryListingDiscoveryRun.idempotency_key == clean_key,
        )
        .first()
    )
    if existing is not None:
        if existing.tenant_id != tenant_id or existing.campaign_id != campaign_id:
            raise ListingDiscoveryError(
                "This listing check request cannot be reused for another location.",
                reason_code="idempotency_scope_mismatch",
                status_code=409,
            )
        return existing, False

    preview = preview_run(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
    )
    campaign, location, organization = _context(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
    )
    plan_code = resolve_plan_economics(organization.plan_type).code
    start_of_day = datetime.combine(datetime.now(UTC).date(), datetime.min.time(), tzinfo=UTC)
    run_count = (
        db.query(DirectoryListingDiscoveryRun)
        .filter(
            DirectoryListingDiscoveryRun.organization_id == organization_id,
            DirectoryListingDiscoveryRun.created_at >= start_of_day,
        )
        .count()
    )
    if run_count >= PLAN_DAILY_LIMITS[plan_code]:
        raise ListingDiscoveryError(
            "This account has reached its public-listing check limit for today.",
            reason_code="daily_listing_discovery_limit_reached",
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
        quantity=1,
        idempotency_key=f"directory-listing-discovery:{organization_id}:{clean_key}",
        business_location_id=location.id,
        campaign_id=campaign.id,
    )
    now = datetime.now(UTC)
    run = DirectoryListingDiscoveryRun(
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign.id,
        business_location_id=location.id,
        idempotency_key=clean_key,
        status="queued",
        provider_name=PROVIDER_NAME,
        credential_owner=owner,
        radius_km=RADIUS_KM,
        result_limit=RESULT_LIMIT,
        reservation_id=reservation.id,
        estimated_cost=Decimal(reservation.estimated_cost),
        estimated_credit_units=int(reservation.customer_credit_units or 0),
        requested_by_user_id=requested_by_user_id,
        created_at=now,
        updated_at=now,
    )
    db.add(run)
    db.flush()
    job_service.create_job(
        db,
        tenant_id=tenant_id,
        job_type=JOB_TYPE,
        entity_type="directory_listing_discovery_run",
        entity_id=run.id,
        idempotency_key=f"directory-listing-discovery-dispatch:{run.id}",
        payload={"tenant_id": tenant_id, "run_id": run.id},
        max_retries=2,
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        concurrent = (
            db.query(DirectoryListingDiscoveryRun)
            .filter(
                DirectoryListingDiscoveryRun.organization_id == organization_id,
                DirectoryListingDiscoveryRun.idempotency_key == clean_key,
            )
            .first()
        )
        if concurrent is not None:
            return concurrent, False
        release_provider_cost(db, reservation=reservation)
        raise
    db.refresh(run)
    return run, True


def dispatch_run(
    db: Session,
    *,
    tenant_id: str,
    run_id: str,
    job_id: str | None = None,
    expected_worker_id: str | None = None,
) -> dict[str, Any]:
    with job_service.serialized_provider_run_dispatch(
        db,
        scope=f"directory-listing-discovery:{run_id}",
    ) as durable_fence:
        return _dispatch_run_serialized(
            db,
            tenant_id=tenant_id,
            run_id=run_id,
            durable_fence=durable_fence,
            job_id=job_id,
            expected_worker_id=expected_worker_id,
        )


def _dispatch_run_serialized(
    db: Session,
    *,
    tenant_id: str,
    run_id: str,
    durable_fence: bool,
    job_id: str | None,
    expected_worker_id: str | None,
) -> dict[str, Any]:
    # The run row is the durable dispatch claim.  Claiming under a row lock
    # prevents two workers (including a reclaimed durable job or a manual
    # run-now request) from making the same paid provider call.
    run = (
        db.query(DirectoryListingDiscoveryRun)
        .filter(DirectoryListingDiscoveryRun.id == run_id)
        .populate_existing()
        .with_for_update()
        .one_or_none()
    )
    if run is None or run.tenant_id != tenant_id:
        raise ValueError("Public listing check was not found.")
    if run.status in {"completed", "failed"}:
        return serialize_run(run)
    if run.status == "running":
        if durable_fence:
            return _fail_stale_dispatch_claim(db, run)
        return serialize_run(run)

    location = (
        db.query(BusinessLocation)
        .filter(BusinessLocation.id == run.business_location_id)
        .populate_existing()
        .one_or_none()
    )
    if location is None or location.latitude is None or location.longitude is None:
        return _fail_run(db, run, "location_unavailable")
    run.status = "running"
    run.started_at = run.started_at or datetime.now(UTC)
    run.updated_at = datetime.now(UTC)
    db.commit()
    try:
        if job_id is not None and expected_worker_id is not None:
            job_service.lock_claimed_job(
                db,
                job_id=job_id,
                expected_worker_id=expected_worker_id,
            )
        if not run.reservation_id:
            raise CostEconomicsError(
                "This paid update does not have a saved cost reservation.",
                reason_code="provider_reservation_required",
                status_code=409,
            )
        authorize_reserved_provider_dispatch(
            db,
            reservation=run.reservation_id,
        )
        # Refresh the provider input after the authorization helper locks the
        # current active location/campaign mapping.
        location = (
            db.query(BusinessLocation)
            .filter(BusinessLocation.id == run.business_location_id)
            .populate_existing()
            .one_or_none()
        )
        if location is None or location.latitude is None or location.longitude is None:
            raise CostEconomicsError(
                "This business location is not ready for a paid update.",
                reason_code="active_business_location_required_for_provider_work",
                status_code=409,
            )
    except CostEconomicsError as exc:
        return _fail_run(db, run, exc.reason_code, message=str(exc))
    provider_call_started = False
    provider_result_received = False
    reported_cost: Decimal | None = None
    try:
        credentials = resolve_provider_credentials(db, run.organization_id, PROVIDER_NAME)
        login = str(credentials.get("login") or credentials.get("username") or "").strip()
        password = str(credentials.get("password") or "")
        provider = DataForSeoBusinessListingsProvider(login=login, password=password)
        provider_call_started = True
        result = provider.search(
            business_name=location.name,
            latitude=float(location.latitude),
            longitude=float(location.longitude),
            radius_km=float(run.radius_km),
            limit=run.result_limit,
        )
        provider_result_received = True
        reported_cost = Decimal(str(result.get("cost") or run.estimated_cost))
        records = _relevant_records(location, list(result.get("items") or []))
        listing_inventory_service.upsert_discovered_listings(
            db,
            tenant_id=tenant_id,
            campaign_id=run.campaign_id,
            records=records,
        )
        actual_cost = reported_cost
        if run.reservation_id:
            reservation = db.get(CostLedgerEntry, run.reservation_id)
            if reservation is not None:
                reconcile_provider_cost(
                    db,
                    reservation=reservation,
                    provider_reported_cost=actual_cost,
                )
        run = db.get(DirectoryListingDiscoveryRun, run.id)
        run.status = "completed"
        run.result_count = len(records)
        run.provider_reported_cost = actual_cost
        run.error_code = None
        run.error_message = None
        run.completed_at = datetime.now(UTC)
        run.updated_at = run.completed_at
        db.commit()
        db.refresh(run)
        return serialize_run(run)
    except Exception:
        db.rollback()
        run = db.get(DirectoryListingDiscoveryRun, run_id)
        if run is None:
            raise
        if provider_call_started and run.reservation_id:
            reservation = db.get(CostLedgerEntry, run.reservation_id)
            if reservation is not None:
                reconcile_provider_cost(
                    db,
                    reservation=reservation,
                    # Once the paid request may have left this process, a timeout
                    # cannot be treated as free work. Prefer a returned provider
                    # amount; otherwise conservatively settle the reserved estimate.
                    provider_reported_cost=(
                        reported_cost
                        if provider_result_received and reported_cost is not None
                        else Decimal(reservation.estimated_cost)
                    ),
                )
        return _fail_run(
            db,
            run,
            "listing_check_failed",
            release_reservation=not provider_call_started,
        )


def _fail_stale_dispatch_claim(
    db: Session,
    run: DirectoryListingDiscoveryRun,
) -> dict[str, Any]:
    """Close an abandoned ambiguous claim without risking a duplicate paid call."""
    if run.reservation_id:
        reservation = db.get(CostLedgerEntry, run.reservation_id)
        if reservation is not None:
            reconcile_provider_cost(
                db,
                reservation=reservation,
                provider_reported_cost=Decimal(reservation.estimated_cost),
            )
    run = db.get(DirectoryListingDiscoveryRun, run.id)
    return _fail_run(
        db,
        run,
        "listing_dispatch_claim_abandoned",
        message=(
            "The public listing check stopped before it could confirm a result. "
            "Start a new check if you still need it."
        ),
        release_reservation=False,
    )


def _fail_run(
    db: Session,
    run: DirectoryListingDiscoveryRun,
    error_code: str,
    *,
    message: str | None = None,
    release_reservation: bool = True,
) -> dict[str, Any]:
    if release_reservation and run.reservation_id:
        reservation = db.get(CostLedgerEntry, run.reservation_id)
        if reservation is not None:
            release_provider_cost(db, reservation=reservation)
    run = db.get(DirectoryListingDiscoveryRun, run.id)
    run.status = "failed"
    run.error_code = error_code
    run.error_message = message or "The public listing check could not be completed. Try again shortly."
    run.completed_at = datetime.now(UTC)
    run.updated_at = run.completed_at
    db.commit()
    db.refresh(run)
    return serialize_run(run)


def get_run(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    run_id: str,
) -> DirectoryListingDiscoveryRun:
    row = (
        db.query(DirectoryListingDiscoveryRun)
        .filter(
            DirectoryListingDiscoveryRun.id == run_id,
            DirectoryListingDiscoveryRun.tenant_id == tenant_id,
            DirectoryListingDiscoveryRun.organization_id == organization_id,
        )
        .first()
    )
    if row is None:
        raise ListingDiscoveryError(
            "Public listing check not found.",
            reason_code="listing_discovery_run_not_found",
            status_code=404,
        )
    return row


def latest_run(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
) -> DirectoryListingDiscoveryRun | None:
    _context(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
    )
    return (
        db.query(DirectoryListingDiscoveryRun)
        .filter(
            DirectoryListingDiscoveryRun.tenant_id == tenant_id,
            DirectoryListingDiscoveryRun.organization_id == organization_id,
            DirectoryListingDiscoveryRun.campaign_id == campaign_id,
        )
        .order_by(DirectoryListingDiscoveryRun.created_at.desc())
        .first()
    )


def serialize_run(run: DirectoryListingDiscoveryRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "campaign_id": run.campaign_id,
        "business_location_id": run.business_location_id,
        "status": run.status,
        "estimated_credits": run.estimated_credit_units,
        "result_count": run.result_count,
        "scope": "supported_public_sources",
        "correction_available": False,
        "error_message": run.error_message,
        "created_at": run.created_at.isoformat(),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


def _relevant_records(
    location: BusinessLocation,
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    target_name = _normalized_name(location.name)
    target_domain = _normalized_domain(location.domain)
    relevant: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        record_name = _normalized_name(str(record.get("business_name") or ""))
        record_domain = _normalized_domain(str(record.get("website_url") or ""))
        if not (
            (target_domain and record_domain == target_domain)
            or (target_name and record_name == target_name)
        ):
            continue
        identity = (str(record.get("source_key") or ""), str(record.get("external_id") or ""))
        if identity in seen:
            continue
        seen.add(identity)
        relevant.append(record)
    source_counts: dict[str, int] = {}
    for record in relevant:
        source_key = str(record.get("source_key") or "")
        source_counts[source_key] = source_counts.get(source_key, 0) + 1
    for record in relevant:
        if source_counts.get(str(record.get("source_key") or ""), 0) > 1:
            record["status"] = "duplicate"
    return relevant


def _normalized_name(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").casefold())


def _normalized_domain(value: str | None) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    parsed = urlparse(text if "://" in text else f"https://{text}")
    host = (parsed.hostname or "").casefold()
    return host[4:] if host.startswith("www.") else host
