"""materialize commercial active-location allowances

Revision ID: 20260814_0155
Revises: 20260814_0154
Create Date: 2026-08-14 23:30:00.000000
"""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
import json
import uuid

from alembic import op
import sqlalchemy as sa


revision = "20260814_0155"
down_revision = "20260814_0154"
branch_labels = None
depends_on = None


_CATALOG_VERSION = "commercial-tiers-2026-08-v2"
_ACTIVATION_CODE = "active_location_allowance"
_ACTIVATION_STATE_OBSERVE = "observe"
_TIER_VERSION = 2
_ACTIVE_LOCATION_CODE = "limit.active_locations"
_PROFILE_DEFINITIONS = {
    "solo": {
        "id": "d4e60a70-9c0c-4b8f-8cf9-4c7f0c690101",
        "display_name": "Solo",
        "active_location_limit": 1,
    },
    "multi_location": {
        "id": "d4e60a70-9c0c-4b8f-8cf9-4c7f0c690102",
        "display_name": "Growth",
        "active_location_limit": 10,
    },
    "enterprise": {
        "id": "d4e60a70-9c0c-4b8f-8cf9-4c7f0c690103",
        "display_name": "Enterprise",
        "active_location_limit": 20,
    },
    "internal_anchor": {
        "id": "d4e60a70-9c0c-4b8f-8cf9-4c7f0c690104",
        "display_name": "Internal Anchor",
        "active_location_limit": 20,
    },
}
_PLAN_ALIASES = {
    "standard": "solo",
    "solo": "solo",
    "pro": "multi_location",
    "growth": "multi_location",
    "multi-location": "multi_location",
    "multi_location": "multi_location",
    "enterprise": "enterprise",
    "internal_anchor": "internal_anchor",
}
_LEGACY_ENTITLEMENT_CODES = (
    "feature.performance_trend",
    "feature.campaign_report",
    "feature.report_export",
    "limit.subaccounts",
    "limit.queue.tokens_per_minute",
    "limit.traffic_fact.provider_calls_monthly",
    "limit.rank.keyword_snapshots_monthly",
    "limit.crawl.pages_monthly",
    "limit.crawl.concurrent_runs",
)
def _stable_hash(payload: dict[str, object]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(serialized.encode("utf-8")).hexdigest()


def _template(plan_code: str) -> list[dict[str, object]]:
    rows = [
        {
            "code": code,
            "value_type": "unlimited",
            "limit_value": None,
            "reset_period": "none",
            "is_enforced": True,
            "config_json": {},
        }
        for code in _LEGACY_ENTITLEMENT_CODES
    ]
    rows.append(
        {
            "code": _ACTIVE_LOCATION_CODE,
            "value_type": "integer",
            "limit_value": int(_PROFILE_DEFINITIONS[plan_code]["active_location_limit"]),
            "reset_period": "none",
            "is_enforced": True,
            "config_json": {
                "catalog_version": _CATALOG_VERSION,
                "unit": "business_location",
            },
        }
    )
    return sorted(rows, key=lambda item: str(item["code"]))


def _legacy_template() -> list[dict[str, object]]:
    return [
        {
            "code": code,
            "value_type": "unlimited",
            "limit_value": None,
            "reset_period": "none",
            "is_enforced": True,
            "config_json": {},
        }
        for code in sorted(_LEGACY_ENTITLEMENT_CODES)
    ]


def _canonical_plan(raw_plan: object) -> str:
    normalized = str(raw_plan or "").strip().lower()
    if normalized not in _PLAN_ALIASES:
        raise RuntimeError(
            "Commercial tier migration preflight failed: unsupported organization "
            f"plan_type '{normalized or '<empty>'}' requires operator review."
        )
    return _PLAN_ALIASES[normalized]


def upgrade() -> None:
    connection = op.get_bind()
    now = datetime.now(UTC)

    tier_profiles = sa.table(
        "tier_profiles",
        sa.column("id", sa.String(length=36)),
        sa.column("tier_code", sa.String(length=50)),
        sa.column("display_name", sa.String(length=120)),
        sa.column("version", sa.Integer()),
        sa.column("entitlement_template_json", sa.JSON()),
        sa.column("deterministic_hash", sa.String(length=64)),
        sa.column("is_active", sa.Boolean()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    organizations = sa.table(
        "organizations",
        sa.column("id", sa.String(length=36)),
        sa.column("plan_type", sa.String(length=30)),
        sa.column("tier_profile_id", sa.String(length=36)),
        sa.column("tier_version", sa.Integer()),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    entitlements = sa.table(
        "entitlements",
        sa.column("id", sa.String(length=36)),
        sa.column("organization_id", sa.String(length=36)),
        sa.column("code", sa.String(length=120)),
        sa.column("value_type", sa.String(length=20)),
        sa.column("limit_value", sa.Integer()),
        sa.column("reset_period", sa.String(length=20)),
        sa.column("is_enforced", sa.Boolean()),
        sa.column("config_json", sa.JSON()),
        sa.column("deterministic_hash", sa.String(length=64)),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )

    organization_query = (
        sa.select(
            organizations.c.id,
            organizations.c.plan_type,
            organizations.c.tier_profile_id,
            organizations.c.tier_version,
        )
        .order_by(organizations.c.id)
        .with_for_update()
    )
    # Fence mixed-version plan changes and lazy allowance bootstrap for the
    # entire preflight/materialization window. Canonical ID ordering prevents
    # multi-organization lock inversion across concurrent deploy work.
    organization_rows = connection.execute(organization_query).mappings().all()
    for organization_row in organization_rows:
        _canonical_plan(organization_row["plan_type"])
        profile_id = str(organization_row["tier_profile_id"] or "").strip()
        if not profile_id or int(organization_row["tier_version"] or 0) != 1:
            raise RuntimeError(
                "Commercial tier migration preflight failed: organization "
                f"{organization_row['id']} is not pointed at an immutable v1 profile."
            )
        profile = connection.execute(
            sa.select(
                tier_profiles.c.id,
                tier_profiles.c.tier_code,
                tier_profiles.c.version,
                tier_profiles.c.entitlement_template_json,
                tier_profiles.c.deterministic_hash,
                tier_profiles.c.is_active,
            ).where(tier_profiles.c.id == profile_id)
        ).mappings().one_or_none()
        profile_tier_code = (
            str(profile["tier_code"] or "").strip().lower()
            if profile is not None
            else ""
        )
        raw_template = profile["entitlement_template_json"] if profile is not None else None
        expected_legacy_hash = _stable_hash(
            {
                "tier_code": profile_tier_code,
                "version": 1,
                "entitlements": _legacy_template(),
            }
        )
        actual_legacy_hash = None
        if isinstance(raw_template, dict) and isinstance(raw_template.get("entitlements"), list):
            actual_legacy_hash = _stable_hash(
                {
                    "tier_code": profile_tier_code,
                    "version": 1,
                    "entitlements": raw_template["entitlements"],
                }
            )
        if (
            profile is None
            or profile_tier_code not in {"standard", "enterprise", "internal_anchor"}
            or int(profile["version"]) != 1
            or not bool(profile["is_active"])
            or str(profile["deterministic_hash"]) != expected_legacy_hash
            or actual_legacy_hash != expected_legacy_hash
        ):
            raise RuntimeError(
                "Commercial tier migration preflight failed: organization "
                f"{organization_row['id']} has an unknown, inactive, or corrupted v1 profile."
            )

        existing_allowance = connection.execute(
            sa.select(
                entitlements.c.id,
                entitlements.c.organization_id,
                entitlements.c.code,
                entitlements.c.value_type,
                entitlements.c.limit_value,
                entitlements.c.reset_period,
                entitlements.c.is_enforced,
                entitlements.c.config_json,
                entitlements.c.deterministic_hash,
            ).where(
                entitlements.c.organization_id == str(organization_row["id"]),
                entitlements.c.code == _ACTIVE_LOCATION_CODE,
            )
        ).mappings().one_or_none()
        if existing_allowance is not None:
            existing_payload = {
                "organization_id": str(existing_allowance["organization_id"]),
                "code": str(existing_allowance["code"]),
                "value_type": str(existing_allowance["value_type"]),
                "limit_value": existing_allowance["limit_value"],
                "reset_period": str(existing_allowance["reset_period"]),
                "is_enforced": bool(existing_allowance["is_enforced"]),
                "config_json": dict(existing_allowance["config_json"] or {}),
            }
            if (
                existing_payload["value_type"] != "integer"
                or existing_payload["limit_value"]
                not in {
                    int(definition["active_location_limit"])
                    for definition in _PROFILE_DEFINITIONS.values()
                }
                or existing_payload["reset_period"] != "none"
                or existing_payload["is_enforced"] is not True
                or existing_payload["config_json"]
                != {"catalog_version": _CATALOG_VERSION, "unit": "business_location"}
                or str(existing_allowance["deterministic_hash"])
                != _stable_hash(existing_payload)
            ):
                raise RuntimeError(
                    "Commercial tier migration preflight failed: organization "
                    f"{organization_row['id']} has a corrupted active-location allowance."
                )

    profiles_to_insert: list[dict[str, object]] = []
    for plan_code, definition in _PROFILE_DEFINITIONS.items():
        template_rows = _template(plan_code)
        profile_hash = _stable_hash(
            {
                "tier_code": plan_code,
                "version": _TIER_VERSION,
                "entitlements": template_rows,
            }
        )
        existing = connection.execute(
            sa.select(
                tier_profiles.c.id,
                tier_profiles.c.deterministic_hash,
                tier_profiles.c.is_active,
                tier_profiles.c.entitlement_template_json,
            ).where(
                tier_profiles.c.tier_code == plan_code,
                tier_profiles.c.version == _TIER_VERSION,
            )
        ).mappings().one_or_none()
        if existing is not None:
            raw_template = existing["entitlement_template_json"]
            actual_hash = None
            if isinstance(raw_template, dict) and isinstance(raw_template.get("entitlements"), list):
                actual_hash = _stable_hash(
                    {
                        "tier_code": plan_code,
                        "version": _TIER_VERSION,
                        "entitlements": raw_template["entitlements"],
                    }
                )
            if (
                str(existing["id"]) != str(definition["id"])
                or str(existing["deterministic_hash"]) != profile_hash
                or actual_hash != profile_hash
                or not bool(existing["is_active"])
            ):
                raise RuntimeError(
                    "Commercial tier profile preflight failed: an existing canonical "
                    f"{plan_code} v{_TIER_VERSION} profile has a different ID/hash or is inactive."
                )
            continue

        preferred_id = str(definition["id"])
        id_owner = connection.execute(
            sa.select(tier_profiles.c.tier_code).where(tier_profiles.c.id == preferred_id)
        ).scalar_one_or_none()
        if id_owner is not None:
            raise RuntimeError(
                "Commercial tier profile preflight failed: canonical profile ID "
                f"{preferred_id} is already used by {id_owner}."
            )
        hash_owner = connection.execute(
            sa.select(tier_profiles.c.id).where(
                tier_profiles.c.deterministic_hash == profile_hash
            )
        ).scalar_one_or_none()
        if hash_owner is not None:
            raise RuntimeError(
                "Commercial tier profile preflight failed: canonical profile hash "
                f"for {plan_code} is already used by {hash_owner}."
            )
        profiles_to_insert.append(
            {
                "id": preferred_id,
                "tier_code": plan_code,
                "display_name": str(definition["display_name"]),
                "version": _TIER_VERSION,
                "entitlement_template_json": {"entitlements": template_rows},
                "deterministic_hash": profile_hash,
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            }
        )

    for values in profiles_to_insert:
        connection.execute(tier_profiles.insert().values(**values))

    op.create_table(
        "commercial_feature_activations",
        sa.Column("code", sa.String(length=80), primary_key=True),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("catalog_version", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state IN ('observe', 'enforced')",
            name="ck_commercial_feature_activations_state",
        ),
    )
    commercial_feature_activations = sa.table(
        "commercial_feature_activations",
        sa.column("code", sa.String(length=80)),
        sa.column("state", sa.String(length=20)),
        sa.column("catalog_version", sa.String(length=80)),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    connection.execute(
        commercial_feature_activations.insert().values(
            code=_ACTIVATION_CODE,
            state=_ACTIVATION_STATE_OBSERVE,
            catalog_version=_CATALOG_VERSION,
            created_at=now,
            updated_at=now,
        )
    )
    if connection.dialect.name == "postgresql":
        op.execute("ALTER TABLE commercial_feature_activations ENABLE ROW LEVEL SECURITY")
        # PostgreSQL requires UPDATE privilege and an UPDATE visibility policy
        # for SELECT ... FOR SHARE. Grant the app role only the harmless
        # updated_at column, and make the policy's WITH CHECK false so the lock
        # is permitted but every actual row mutation is rejected.
        op.execute(
            "GRANT SELECT, UPDATE (updated_at) "
            "ON TABLE commercial_feature_activations TO lsos_app"
        )
        op.execute(
            "CREATE POLICY commercial_feature_activations_global_read "
            "ON commercial_feature_activations FOR SELECT TO lsos_app USING (true)"
        )
        op.execute(
            "CREATE POLICY commercial_feature_activations_lock_only "
            "ON commercial_feature_activations FOR UPDATE TO lsos_app "
            "USING (true) WITH CHECK (false)"
        )

    for organization_row in organization_rows:
        organization_id = str(organization_row["id"])
        plan_code = _canonical_plan(organization_row["plan_type"])

        existing_rows = {
            str(row["code"]): row
            for row in connection.execute(
                sa.select(entitlements.c.id, entitlements.c.code).where(
                    entitlements.c.organization_id == organization_id
                )
            ).mappings().all()
        }
        for item in _template(plan_code):
            entitlement_payload = {
                "organization_id": organization_id,
                "code": str(item["code"]),
                "value_type": str(item["value_type"]),
                "limit_value": item["limit_value"],
                "reset_period": str(item["reset_period"]),
                "is_enforced": bool(item["is_enforced"]),
                "config_json": dict(item.get("config_json") or {}),
            }
            deterministic_hash = _stable_hash(entitlement_payload)
            existing_row = existing_rows.get(str(item["code"]))
            if existing_row is None:
                connection.execute(
                    entitlements.insert().values(
                        id=str(uuid.uuid4()),
                        **entitlement_payload,
                        deterministic_hash=deterministic_hash,
                        created_at=now,
                        updated_at=now,
                    )
                )
                continue
            if str(item["code"]) != _ACTIVE_LOCATION_CODE:
                # Preserve operator-configured legacy limits and their ledger
                # semantics. COM1.3A only owns active-location capacity.
                continue
            connection.execute(
                entitlements.update()
                .where(entitlements.c.id == str(existing_row["id"]))
                .values(
                    value_type=entitlement_payload["value_type"],
                    limit_value=entitlement_payload["limit_value"],
                    reset_period=entitlement_payload["reset_period"],
                    is_enforced=entitlement_payload["is_enforced"],
                    config_json=entitlement_payload["config_json"],
                    deterministic_hash=deterministic_hash,
                    updated_at=now,
                )
            )


def downgrade() -> None:
    # This is an expand/observe revision: upgrade never changes organization
    # plan aliases or tier-profile pointers. Rollback therefore removes only
    # the activation switch. Seeded catalog rows and materialized allowance
    # rows are additive and intentionally retained so no customer, operator,
    # or usage-ledger state is destroyed by an app/database rollback.
    op.drop_table("commercial_feature_activations")
