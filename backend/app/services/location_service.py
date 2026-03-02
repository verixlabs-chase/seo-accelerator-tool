"""
Canonical write surface for execution-layer locations.
All future location create/update flows MUST call this service.
Direct DB writes to locations outside this service are prohibited.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from fastapi import HTTPException, status
from sqlalchemy.orm import Session


UNSET = object()

_METADATA = sa.MetaData()
_LOCATIONS_TABLE = sa.Table(
    "locations",
    _METADATA,
    sa.Column("id", sa.String(length=36)),
    sa.Column("organization_id", sa.String(length=36)),
    sa.Column("portfolio_id", sa.String(length=36)),
    sa.Column("sub_account_id", sa.String(length=36)),
    sa.Column("campaign_id", sa.String(length=36)),
    sa.Column("location_code", sa.String(length=64)),
    sa.Column("name", sa.String(length=160)),
    sa.Column("country_code", sa.String(length=2)),
    sa.Column("region", sa.String(length=120)),
    sa.Column("city", sa.String(length=120)),
    sa.Column("lat", sa.Numeric(9, 6)),
    sa.Column("lng", sa.Numeric(9, 6)),
    sa.Column("status", sa.String(length=20)),
    sa.Column("business_location_id", sa.String(length=36)),
    sa.Column("created_at", sa.DateTime(timezone=True)),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
)
_BUSINESS_LOCATIONS_TABLE = sa.Table(
    "business_locations",
    _METADATA,
    sa.Column("id", sa.String(length=36)),
    sa.Column("organization_id", sa.String(length=36)),
)


class LocationWriteService:
    def create_location(
        self,
        db: Session,
        *,
        organization_id: str,
        sub_account_id: str,
        location_code: str,
        name: str,
        country_code: str,
        portfolio_id: str | None = None,
        campaign_id: str | None = None,
        region: str | None = None,
        city: str | None = None,
        lat: float | None = None,
        lng: float | None = None,
        status_value: str = "active",
        business_location_id: str | None = None,
    ) -> dict[str, object]:
        self._validate_business_location_scope(
            db,
            organization_id=organization_id,
            business_location_id=business_location_id,
        )

        now = datetime.now(UTC)
        location_id = str(uuid.uuid4())
        normalized_status = status_value.strip().lower() or "active"
        normalized_location_code = location_code.strip()
        normalized_name = name.strip()
        normalized_country_code = country_code.strip().upper()
        normalized_region = _normalize_optional(region)
        normalized_city = _normalize_optional(city)

        db.execute(
            sa.insert(_LOCATIONS_TABLE).values(
                id=location_id,
                organization_id=organization_id,
                portfolio_id=portfolio_id,
                sub_account_id=sub_account_id,
                campaign_id=campaign_id,
                location_code=normalized_location_code,
                name=normalized_name,
                country_code=normalized_country_code,
                region=normalized_region,
                city=normalized_city,
                lat=lat,
                lng=lng,
                status=normalized_status,
                business_location_id=business_location_id,
                created_at=now,
                updated_at=now,
            )
        )

        return {
            "id": location_id,
            "organization_id": organization_id,
            "portfolio_id": portfolio_id,
            "sub_account_id": sub_account_id,
            "campaign_id": campaign_id,
            "location_code": normalized_location_code,
            "name": normalized_name,
            "country_code": normalized_country_code,
            "region": normalized_region,
            "city": normalized_city,
            "lat": lat,
            "lng": lng,
            "status": normalized_status,
            "business_location_id": business_location_id,
            "created_at": now,
            "updated_at": now,
        }

    def update_location(
        self,
        db: Session,
        *,
        location_id: str,
        organization_id: str,
        name: str | object = UNSET,
        business_location_id: str | None | object = UNSET,
    ) -> dict[str, object]:
        current = db.execute(
            sa.select(
                _LOCATIONS_TABLE.c.id,
                _LOCATIONS_TABLE.c.organization_id,
                _LOCATIONS_TABLE.c.name,
                _LOCATIONS_TABLE.c.business_location_id,
                _LOCATIONS_TABLE.c.created_at,
                _LOCATIONS_TABLE.c.updated_at,
            ).where(_LOCATIONS_TABLE.c.id == location_id)
        ).mappings().first()
        if current is None or current["organization_id"] != organization_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"message": "Location not found.", "reason_code": "location_not_found"},
            )

        next_name = current["name"]
        next_business_location_id = current["business_location_id"]
        next_updated_at = current["updated_at"]
        update_values: dict[str, object] = {}

        if name is not UNSET:
            normalized_name = str(name).strip()
            update_values["name"] = normalized_name
            next_name = normalized_name

        if business_location_id is not UNSET:
            self._validate_business_location_scope(
                db,
                organization_id=organization_id,
                business_location_id=business_location_id,
            )
            update_values["business_location_id"] = business_location_id
            next_business_location_id = business_location_id

        if update_values:
            next_updated_at = datetime.now(UTC)
            update_values["updated_at"] = next_updated_at
            db.execute(
                sa.update(_LOCATIONS_TABLE)
                .where(_LOCATIONS_TABLE.c.id == location_id)
                .values(**update_values)
            )

        return {
            "id": location_id,
            "organization_id": organization_id,
            "name": next_name,
            "business_location_id": next_business_location_id,
            "created_at": current["created_at"],
            "updated_at": next_updated_at,
        }

    def _validate_business_location_scope(
        self,
        db: Session,
        *,
        organization_id: str,
        business_location_id: str | None,
    ) -> None:
        if business_location_id is None:
            return

        business_location_org_id = db.execute(
            sa.select(_BUSINESS_LOCATIONS_TABLE.c.organization_id).where(
                _BUSINESS_LOCATIONS_TABLE.c.id == business_location_id
            )
        ).scalar_one_or_none()
        if business_location_org_id is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "message": "BusinessLocation not found.",
                    "reason_code": "business_location_not_found",
                },
            )
        if business_location_org_id != organization_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "message": "BusinessLocation is outside organization scope.",
                    "reason_code": "business_location_org_mismatch",
                },
            )


def _normalize_optional(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None
