"""seed tier profiles and backfill organization entitlements

Revision ID: 20260728_0073
Revises: 20260728_0072
Create Date: 2026-07-28 14:30:00.000000
"""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
import json
import uuid

from alembic import op
import sqlalchemy as sa


revision = "20260728_0073"
down_revision = "20260728_0072"
branch_labels = None
depends_on = None


_TIER_PROFILE_IDS = {
    "standard": "d4e60a70-9c0c-4b8f-8cf9-4c7f0c690001",
    "enterprise": "d4e60a70-9c0c-4b8f-8cf9-4c7f0c690002",
    "internal_anchor": "d4e60a70-9c0c-4b8f-8cf9-4c7f0c690003",
}
_TIER_DISPLAY_NAMES = {
    "standard": "Standard",
    "enterprise": "Enterprise",
    "internal_anchor": "Internal Anchor",
}
_ENTITLEMENT_CODES = (
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


def _entitlement_template() -> list[dict[str, object]]:
    return [
        {
            "code": code,
            "value_type": "unlimited",
            "limit_value": None,
            "reset_period": "none",
            "is_enforced": True,
            "config_json": {},
        }
        for code in sorted(_ENTITLEMENT_CODES)
    ]


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

    template_rows = _entitlement_template()
    resolved_profiles: dict[str, str] = {}
    for tier_code, preferred_id in _TIER_PROFILE_IDS.items():
        existing = connection.execute(
            sa.select(tier_profiles.c.id).where(
                tier_profiles.c.tier_code == tier_code,
                tier_profiles.c.version == 1,
            )
        ).first()
        profile_id = str(existing[0]) if existing is not None else preferred_id
        if existing is None:
            profile_hash = _stable_hash(
                {
                    "tier_code": tier_code,
                    "version": 1,
                    "entitlements": template_rows,
                }
            )
            connection.execute(
                tier_profiles.insert().values(
                    id=profile_id,
                    tier_code=tier_code,
                    display_name=_TIER_DISPLAY_NAMES[tier_code],
                    version=1,
                    entitlement_template_json={"entitlements": template_rows},
                    deterministic_hash=profile_hash,
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                )
            )
        resolved_profiles[tier_code] = profile_id

    organization_rows = connection.execute(
        sa.select(
            organizations.c.id,
            organizations.c.plan_type,
            organizations.c.tier_profile_id,
        )
    ).all()
    for organization_id, plan_type, tier_profile_id in organization_rows:
        resolved_tier_code = str(plan_type or "standard").strip().lower()
        if resolved_tier_code not in resolved_profiles:
            resolved_tier_code = "standard"
        resolved_profile_id = str(tier_profile_id) if tier_profile_id else resolved_profiles[resolved_tier_code]
        if tier_profile_id is None:
            connection.execute(
                organizations.update()
                .where(organizations.c.id == str(organization_id))
                .values(
                    tier_profile_id=resolved_profile_id,
                    tier_version=1,
                    updated_at=now,
                )
            )

        existing_codes = {
            str(row[0])
            for row in connection.execute(
                sa.select(entitlements.c.code).where(
                    entitlements.c.organization_id == str(organization_id)
                )
            ).all()
        }
        for item in template_rows:
            code = str(item["code"])
            if code in existing_codes:
                continue
            entitlement_payload = {
                "organization_id": str(organization_id),
                "code": code,
                "value_type": "unlimited",
                "limit_value": None,
                "reset_period": "none",
                "is_enforced": True,
                "config_json": {},
            }
            connection.execute(
                entitlements.insert().values(
                    id=str(uuid.uuid4()),
                    **entitlement_payload,
                    deterministic_hash=_stable_hash(entitlement_payload),
                    created_at=now,
                    updated_at=now,
                )
            )


def downgrade() -> None:
    # This migration materializes operational account data. Removing those rows
    # could erase later billing changes, so a downgrade intentionally preserves it.
    pass
