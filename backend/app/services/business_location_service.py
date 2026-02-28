from __future__ import annotations

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session


_METADATA = sa.MetaData()
_BUSINESS_LOCATIONS_TABLE = sa.Table(
    "business_locations",
    _METADATA,
    sa.Column("id", sa.String(length=36)),
    sa.Column("organization_id", sa.String(length=36)),
    sa.Column("name", sa.String(length=255)),
    sa.Column("domain", sa.String(length=255)),
    sa.Column("primary_city", sa.String(length=255)),
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


def create_business_location_with_portfolio(
    db: Session,
    *,
    organization_id: str,
    name: str,
    domain: str | None,
    primary_city: str | None,
) -> dict[str, object]:
    now = datetime.now(UTC)
    business_location_id = str(uuid.uuid4())
    normalized_name = name.strip()
    normalized_domain = _normalize_optional(domain)
    normalized_city = _normalize_optional(primary_city)

    try:
        db.execute(
            sa.insert(_BUSINESS_LOCATIONS_TABLE).values(
                id=business_location_id,
                organization_id=organization_id,
                name=normalized_name,
                domain=normalized_domain,
                primary_city=normalized_city,
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
        db.execute(
            sa.insert(_PORTFOLIOS_TABLE).values(
                id=str(uuid.uuid4()),
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

    return {
        "id": business_location_id,
        "organization_id": organization_id,
        "name": normalized_name,
        "domain": normalized_domain,
        "primary_city": normalized_city,
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }


def _build_internal_portfolio_name(name: str) -> str:
    prefix = "Internal Portfolio - "
    max_name_len = 160 - len(prefix)
    return f"{prefix}{name[:max_name_len].rstrip()}"


def _build_internal_portfolio_code(business_location_id: str) -> str:
    return f"bl-{business_location_id.replace('-', '')}"


def _normalize_optional(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None
