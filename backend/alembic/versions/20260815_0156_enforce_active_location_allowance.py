"""enforce commercial active-location allowances

Revision ID: 20260815_0156
Revises: 20260814_0155
Create Date: 2026-08-15 14:00:00.000000
"""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
import json

from alembic import op
import sqlalchemy as sa


revision = "20260815_0156"
down_revision = "20260814_0155"
branch_labels = None
depends_on = None


_ACTIVATION_CODE = "active_location_allowance"
_CATALOG_VERSION = "commercial-tiers-2026-08-v2"
_ACTIVE_LOCATION_CODE = "limit.active_locations"
_OBSERVE = "observe"
_ENFORCED = "enforced"
_PLAN_LIMITS = {
    "standard": 1,
    "solo": 1,
    "pro": 10,
    "growth": 10,
    "multi-location": 10,
    "multi_location": 10,
    "enterprise": 20,
    "internal_anchor": 20,
}


def _stable_hash(payload: dict[str, object]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(serialized.encode("utf-8")).hexdigest()


def _lock_commercial_writes(connection: sa.Connection) -> None:
    if connection.dialect.name == "postgresql":
        # Runtime authorization always locks Organization before Entitlement and
        # the activation singleton. Take the deployment fence in that same
        # order so the state flip drains in-flight decisions without deadlock.
        op.execute("LOCK TABLE organizations IN SHARE ROW EXCLUSIVE MODE")


def _activation_row(connection: sa.Connection, table: sa.Table) -> sa.RowMapping:
    query = sa.select(
        table.c.code,
        table.c.state,
        table.c.catalog_version,
    ).where(table.c.code == _ACTIVATION_CODE)
    if connection.dialect.name == "postgresql":
        query = query.with_for_update()
    row = connection.execute(query).mappings().one_or_none()
    if row is None:
        raise RuntimeError(
            "Active-location enforcement preflight failed: the activation record is missing."
        )
    if str(row["catalog_version"]) != _CATALOG_VERSION:
        raise RuntimeError(
            "Active-location enforcement preflight failed: the activation catalog is invalid."
        )
    return row


def _validate_allowances(connection: sa.Connection) -> None:
    organizations = sa.table(
        "organizations",
        sa.column("id", sa.String(length=36)),
        sa.column("plan_type", sa.String(length=30)),
    )
    entitlements = sa.table(
        "entitlements",
        sa.column("organization_id", sa.String(length=36)),
        sa.column("code", sa.String(length=120)),
        sa.column("value_type", sa.String(length=20)),
        sa.column("limit_value", sa.Integer()),
        sa.column("reset_period", sa.String(length=20)),
        sa.column("is_enforced", sa.Boolean()),
        sa.column("config_json", sa.JSON()),
        sa.column("deterministic_hash", sa.String(length=64)),
    )
    organization_query = sa.select(
        organizations.c.id,
        organizations.c.plan_type,
    ).order_by(organizations.c.id)
    if connection.dialect.name == "postgresql":
        organization_query = organization_query.with_for_update()
    organization_rows = connection.execute(organization_query).mappings().all()

    expected_config = {
        "catalog_version": _CATALOG_VERSION,
        "unit": "business_location",
    }
    for organization in organization_rows:
        organization_id = str(organization["id"])
        plan_type = str(organization["plan_type"] or "").strip().lower()
        expected_limit = _PLAN_LIMITS.get(plan_type)
        if expected_limit is None:
            raise RuntimeError(
                "Active-location enforcement preflight failed: organization "
                f"{organization_id} has an unsupported commercial plan."
            )

        entitlement_query = sa.select(
            entitlements.c.organization_id,
            entitlements.c.code,
            entitlements.c.value_type,
            entitlements.c.limit_value,
            entitlements.c.reset_period,
            entitlements.c.is_enforced,
            entitlements.c.config_json,
            entitlements.c.deterministic_hash,
        ).where(
            entitlements.c.organization_id == organization_id,
            entitlements.c.code == _ACTIVE_LOCATION_CODE,
        )
        if connection.dialect.name == "postgresql":
            entitlement_query = entitlement_query.with_for_update()
        entitlement = connection.execute(entitlement_query).mappings().one_or_none()
        if entitlement is None:
            raise RuntimeError(
                "Active-location enforcement preflight failed: organization "
                f"{organization_id} is missing its active-location allowance."
            )

        payload = {
            "organization_id": organization_id,
            "code": _ACTIVE_LOCATION_CODE,
            "value_type": str(entitlement["value_type"]),
            "limit_value": entitlement["limit_value"],
            "reset_period": str(entitlement["reset_period"]),
            "is_enforced": bool(entitlement["is_enforced"]),
            "config_json": dict(entitlement["config_json"] or {}),
        }
        if (
            payload["value_type"] != "integer"
            or payload["limit_value"] != expected_limit
            or payload["reset_period"] != "none"
            or payload["is_enforced"] is not True
            or payload["config_json"] != expected_config
            or str(entitlement["deterministic_hash"]) != _stable_hash(payload)
        ):
            raise RuntimeError(
                "Active-location enforcement preflight failed: organization "
                f"{organization_id} has a stale or corrupted active-location allowance."
            )


def _set_state(*, expected: str, target: str, validate_allowances: bool) -> None:
    connection = op.get_bind()
    _lock_commercial_writes(connection)
    if validate_allowances:
        _validate_allowances(connection)

    activations = sa.table(
        "commercial_feature_activations",
        sa.column("code", sa.String(length=80)),
        sa.column("state", sa.String(length=20)),
        sa.column("catalog_version", sa.String(length=80)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    row = _activation_row(connection, activations)
    if str(row["state"]) != expected:
        raise RuntimeError(
            "Active-location enforcement preflight failed: expected activation state "
            f"'{expected}', found '{row['state']}'."
        )
    result = connection.execute(
        activations.update()
        .where(
            activations.c.code == _ACTIVATION_CODE,
            activations.c.state == expected,
            activations.c.catalog_version == _CATALOG_VERSION,
        )
        .values(state=target, updated_at=datetime.now(UTC))
    )
    if result.rowcount != 1:
        raise RuntimeError(
            "Active-location enforcement state changed during the deployment boundary."
        )


def upgrade() -> None:
    _set_state(expected=_OBSERVE, target=_ENFORCED, validate_allowances=True)


def downgrade() -> None:
    _set_state(expected=_ENFORCED, target=_OBSERVE, validate_allowances=False)
