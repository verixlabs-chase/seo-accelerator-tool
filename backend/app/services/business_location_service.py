from __future__ import annotations

from time import monotonic
import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models.business_location import BusinessLocation
from app.models.campaign import Campaign
from app.models.location import Location, LocationStatus
from app.models.portfolio import Portfolio
from app.models.sub_account import SubAccount
from app.services.location_service import LocationWriteService
from app.services.location_allowance_service import (
    assert_active_location_capacity,
    lock_organization_for_location_allowance,
)
from app.services.operational_telemetry_service import record_service_operation


_METADATA = sa.MetaData()
_BUSINESS_LOCATIONS_TABLE = sa.Table(
    "business_locations",
    _METADATA,
    sa.Column("id", sa.String(length=36)),
    sa.Column("organization_id", sa.String(length=36)),
    sa.Column("sub_account_id", sa.String(length=36)),
    sa.Column("name", sa.String(length=255)),
    sa.Column("domain", sa.String(length=255)),
    sa.Column("primary_city", sa.String(length=255)),
    sa.Column("city", sa.String(length=120)),
    sa.Column("region", sa.String(length=120)),
    sa.Column("country_code", sa.String(length=2)),
    sa.Column("address_line1", sa.String(length=255)),
    sa.Column("postal_code", sa.String(length=32)),
    sa.Column("latitude", sa.Numeric(9, 6)),
    sa.Column("longitude", sa.Numeric(9, 6)),
    sa.Column("coordinate_precision", sa.String(length=30)),
    sa.Column("coordinate_source", sa.String(length=50)),
    sa.Column("provider_location_code", sa.String(length=32)),
    sa.Column("provider_location_name", sa.String(length=255)),
    sa.Column("provider_location_type", sa.String(length=50)),
    sa.Column("provider_location_resolved_at", sa.DateTime(timezone=True)),
    sa.Column("status", sa.String(length=50)),
    sa.Column("created_at", sa.DateTime(timezone=True)),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
)
_PORTFOLIOS_TABLE = sa.Table(
    "portfolios",
    _METADATA,
    sa.Column("id", sa.String(length=36)),
    sa.Column("organization_id", sa.String(length=36)),
    sa.Column("business_location_id", sa.String(length=36)),
    sa.Column("name", sa.String(length=160)),
    sa.Column("code", sa.String(length=64)),
    sa.Column("status", sa.String(length=20)),
    sa.Column("timezone", sa.String(length=80)),
    sa.Column("default_sla_tier", sa.String(length=20)),
    sa.Column("archived_at", sa.DateTime(timezone=True)),
    sa.Column("created_at", sa.DateTime(timezone=True)),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
)


class BusinessLocationConflictError(RuntimeError):
    pass


class BusinessLocationInvariantError(RuntimeError):
    pass


ALLOWED_BUSINESS_LOCATION_STATUSES = {"active", "suspended", "archived"}


def create_business_location_with_portfolio(
    db: Session,
    *,
    organization_id: str,
    name: str,
    domain: str | None,
    primary_city: str | None,
    city: str | None = None,
    region: str | None = None,
    country_code: str = "US",
    address_line1: str | None = None,
    postal_code: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    sub_account_id: str | None = None,
) -> dict[str, object]:
    started_at = monotonic()
    success = False
    try:
        assert_active_location_capacity(
            db,
            organization_id=organization_id,
            requested_delta=1,
        )
        now = datetime.now(UTC)
        business_location_id = str(uuid.uuid4())
        normalized_name = name
        normalized_domain = _normalize_optional(domain)
        normalized_city = _normalize_optional(city) or _normalize_optional(primary_city)
        normalized_region = _normalize_optional(region)
        normalized_country_code = country_code.strip().upper()
        normalized_address_line1 = _normalize_optional(address_line1)
        normalized_postal_code = _normalize_optional(postal_code)
        _validate_coordinates(latitude, longitude)
        coordinate_precision = "exact" if normalized_address_line1 and latitude is not None else (
            "manual" if latitude is not None else None
        )
        coordinate_source = "manual" if latitude is not None else None
        resolved_sub_account = _resolve_active_subaccount(
            db,
            organization_id=organization_id,
            sub_account_id=sub_account_id,
        )

        try:
            db.execute(
                sa.insert(_BUSINESS_LOCATIONS_TABLE).values(
                    id=business_location_id,
                    organization_id=organization_id,
                    sub_account_id=resolved_sub_account.id if resolved_sub_account else None,
                    name=normalized_name,
                    domain=normalized_domain,
                    primary_city=normalized_city,
                    city=normalized_city,
                    region=normalized_region,
                    country_code=normalized_country_code,
                    address_line1=normalized_address_line1,
                    postal_code=normalized_postal_code,
                    latitude=latitude,
                    longitude=longitude,
                    coordinate_precision=coordinate_precision,
                    coordinate_source=coordinate_source,
                    provider_location_code=None,
                    provider_location_name=None,
                    provider_location_type=None,
                    provider_location_resolved_at=None,
                    status="active",
                    created_at=now,
                    updated_at=now,
                )
            )
        except sa.exc.IntegrityError as exc:
            raise BusinessLocationConflictError("business_location_conflict") from exc

        persisted_org_id = db.execute(
            sa.select(_BUSINESS_LOCATIONS_TABLE.c.organization_id).where(_BUSINESS_LOCATIONS_TABLE.c.id == business_location_id)
        ).scalar_one()
        if persisted_org_id != organization_id:
            raise BusinessLocationInvariantError("business_location_org_mismatch")

        try:
            portfolio_id = str(uuid.uuid4())
            db.execute(
                sa.insert(_PORTFOLIOS_TABLE).values(
                    id=portfolio_id,
                    organization_id=organization_id,
                    business_location_id=business_location_id,
                    name=_build_internal_portfolio_name(normalized_name),
                    code=_build_internal_portfolio_code(business_location_id),
                    status="active",
                    timezone="UTC",
                    default_sla_tier="standard",
                    archived_at=None,
                    created_at=now,
                    updated_at=now,
                )
            )
        except sa.exc.IntegrityError as exc:
            raise BusinessLocationConflictError("portfolio_auto_create_conflict") from exc

        execution_location_id: str | None = None
        if resolved_sub_account is not None:
            execution_location = LocationWriteService().create_location(
                db,
                organization_id=organization_id,
                portfolio_id=portfolio_id,
                sub_account_id=resolved_sub_account.id,
                location_code=_build_execution_location_code(business_location_id),
                name=normalized_name,
                country_code=normalized_country_code,
                region=normalized_region,
                city=normalized_city,
                lat=latitude,
                lng=longitude,
                business_location_id=business_location_id,
            )
            execution_location_id = str(execution_location["id"])

        success = True
        return {
            "id": business_location_id,
            "organization_id": organization_id,
            "sub_account_id": resolved_sub_account.id if resolved_sub_account else None,
            "name": normalized_name,
            "domain": normalized_domain,
            "primary_city": normalized_city,
            "city": normalized_city,
            "region": normalized_region,
            "country_code": normalized_country_code,
            "address_line1": normalized_address_line1,
            "postal_code": normalized_postal_code,
            "latitude": latitude,
            "longitude": longitude,
            "coordinate_precision": coordinate_precision,
            "coordinate_source": coordinate_source,
            "provider_location_code": None,
            "provider_location_name": None,
            "provider_location_type": None,
            "provider_location_resolved_at": None,
            "status": "active",
            "created_at": now,
            "updated_at": now,
            "execution_location_id": execution_location_id,
        }
    finally:
        record_service_operation(
            service="business_location_service",
            operation="create_business_location_with_portfolio",
            duration_ms=(monotonic() - started_at) * 1000.0,
            success=success,
            organization_id=organization_id,
        )


def _build_internal_portfolio_name(name: str) -> str:
    prefix = "Internal Portfolio - "
    max_name_len = 160 - len(prefix)
    return f"{prefix}{name[:max_name_len].rstrip()}"


def _build_internal_portfolio_code(business_location_id: str) -> str:
    return f"bl-{business_location_id.replace('-', '')}"


def _build_execution_location_code(business_location_id: str) -> str:
    return f"loc-{business_location_id.replace('-', '')[:24]}"


def update_business_location(
    db: Session,
    *,
    organization_id: str,
    business_location_id: str,
    changes: dict[str, object],
) -> BusinessLocation:
    locked_organization = lock_organization_for_location_allowance(
        db,
        organization_id=organization_id,
    )
    row = (
        db.query(BusinessLocation)
        .filter(
            BusinessLocation.id == business_location_id,
            BusinessLocation.organization_id == organization_id,
        )
        .first()
    )
    if row is None:
        raise BusinessLocationInvariantError("business_location_not_found")

    existing_locations = (
        db.query(Location)
        .filter(
            Location.organization_id == organization_id,
            Location.business_location_id == row.id,
        )
        .all()
    )
    if "sub_account_id" in changes:
        requested_subaccount_id = changes["sub_account_id"]
        if requested_subaccount_id is None and existing_locations:
            raise BusinessLocationInvariantError("subaccount_required_for_linked_location")
        resolved_subaccount = _resolve_active_subaccount(
            db,
            organization_id=organization_id,
            sub_account_id=str(requested_subaccount_id) if requested_subaccount_id else None,
        )
        row.sub_account_id = resolved_subaccount.id if resolved_subaccount else None

    if "name" in changes and changes["name"] is not None:
        row.name = str(changes["name"]).strip()
    if "domain" in changes:
        row.domain = _normalize_optional(str(changes["domain"])) if changes["domain"] is not None else None
    if "city" in changes:
        row.city = _normalize_optional(str(changes["city"])) if changes["city"] is not None else None
        row.primary_city = row.city
    elif "primary_city" in changes:
        row.primary_city = (
            _normalize_optional(str(changes["primary_city"]))
            if changes["primary_city"] is not None
            else None
        )
        row.city = row.primary_city
    if "region" in changes:
        row.region = _normalize_optional(str(changes["region"])) if changes["region"] is not None else None
    if "country_code" in changes and changes["country_code"] is not None:
        row.country_code = str(changes["country_code"]).strip().upper()
    if "address_line1" in changes:
        row.address_line1 = (
            _normalize_optional(str(changes["address_line1"]))
            if changes["address_line1"] is not None
            else None
        )
    if "postal_code" in changes:
        row.postal_code = (
            _normalize_optional(str(changes["postal_code"]))
            if changes["postal_code"] is not None
            else None
        )
    if "latitude" in changes or "longitude" in changes:
        next_latitude = changes.get("latitude", row.latitude)
        next_longitude = changes.get("longitude", row.longitude)
        _validate_coordinates(next_latitude, next_longitude)
        row.latitude = next_latitude
        row.longitude = next_longitude
        if next_latitude is None:
            row.coordinate_precision = None
            row.coordinate_source = None
        else:
            row.coordinate_precision = "exact" if row.address_line1 else "manual"
            row.coordinate_source = "manual"
    if {"city", "primary_city", "region", "country_code"} & changes.keys():
        row.provider_location_code = None
        row.provider_location_name = None
        row.provider_location_type = None
        row.provider_location_resolved_at = None
    if "status" in changes and changes["status"] is not None:
        next_status = str(changes["status"]).strip().lower()
        if next_status not in ALLOWED_BUSINESS_LOCATION_STATUSES:
            raise BusinessLocationInvariantError("business_location_status_invalid")
        if row.status != "active" and next_status == "active":
            assert_active_location_capacity(
                db,
                organization_id=organization_id,
                requested_delta=1,
                locked_organization=locked_organization,
            )
        row.status = next_status

    row.updated_at = datetime.now(UTC)
    portfolio = (
        db.query(Portfolio)
        .filter(
            Portfolio.organization_id == organization_id,
            Portfolio.business_location_id == row.id,
        )
        .first()
    )
    if portfolio is not None:
        portfolio.name = _build_internal_portfolio_name(row.name)
        portfolio.status = "archived" if row.status == "archived" else "active"

    linked_locations = existing_locations
    for location in linked_locations:
        if "sub_account_id" in changes and row.sub_account_id is not None:
            location.sub_account_id = row.sub_account_id
        if portfolio is not None:
            location.portfolio_id = portfolio.id
        if row.status in ALLOWED_BUSINESS_LOCATION_STATUSES:
            location.status = LocationStatus(row.status)
        location.name = row.name
        location.country_code = row.country_code
        location.region = row.region
        location.city = row.city or row.primary_city
        location.lat = row.latitude
        location.lng = row.longitude

    linked_campaigns = (
        db.query(Campaign)
        .filter(
            Campaign.organization_id == organization_id,
            Campaign.business_location_id == row.id,
        )
        .all()
    )
    for campaign in linked_campaigns:
        if "sub_account_id" in changes:
            campaign.sub_account_id = row.sub_account_id
        if portfolio is not None:
            campaign.portfolio_id = portfolio.id

    if row.sub_account_id is not None and not linked_locations:
        LocationWriteService().create_location(
            db,
            organization_id=organization_id,
            portfolio_id=portfolio.id if portfolio else None,
            sub_account_id=row.sub_account_id,
            location_code=_build_execution_location_code(row.id),
            name=row.name,
            country_code=row.country_code,
            region=row.region,
            city=row.city or row.primary_city,
            lat=row.latitude,
            lng=row.longitude,
            status_value=row.status,
            business_location_id=row.id,
        )

    db.flush()
    return row


def _resolve_active_subaccount(
    db: Session,
    *,
    organization_id: str,
    sub_account_id: str | None,
) -> SubAccount | None:
    if sub_account_id is None:
        return None
    row = (
        db.query(SubAccount)
        .filter(
            SubAccount.id == sub_account_id,
            SubAccount.organization_id == organization_id,
        )
        .first()
    )
    if row is None:
        raise BusinessLocationInvariantError("subaccount_not_found")
    if row.status != "active":
        raise BusinessLocationInvariantError("subaccount_inactive")
    return row


def _normalize_optional(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _validate_coordinates(latitude: object, longitude: object) -> None:
    if (latitude is None) != (longitude is None):
        raise BusinessLocationInvariantError("coordinates_must_be_paired")
    if latitude is None:
        return
    lat = float(latitude)
    lng = float(longitude)
    if not -90 <= lat <= 90 or not -180 <= lng <= 180:
        raise BusinessLocationInvariantError("coordinates_out_of_range")
