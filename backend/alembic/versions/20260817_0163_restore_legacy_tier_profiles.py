"""restore immutable legacy tier profiles required by the commercial bridge

Revision ID: 20260817_0163
Revises: 20260817_0162
Create Date: 2026-08-17 14:15:00.000000
"""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
import json

from alembic import op
import sqlalchemy as sa


revision = "20260817_0163"
down_revision = "20260817_0162"
branch_labels = None
depends_on = None


_PROFILE_DEFINITIONS = {
    "standard": {
        "id": "d4e60a70-9c0c-4b8f-8cf9-4c7f0c690001",
        "display_name": "Standard",
    },
    "enterprise": {
        "id": "d4e60a70-9c0c-4b8f-8cf9-4c7f0c690002",
        "display_name": "Enterprise",
    },
    "internal_anchor": {
        "id": "d4e60a70-9c0c-4b8f-8cf9-4c7f0c690003",
        "display_name": "Internal Anchor",
    },
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


def _expected_hash(tier_code: str) -> str:
    return _stable_hash(
        {
            "tier_code": tier_code,
            "version": 1,
            "entitlements": _legacy_template(),
        }
    )


def _validate_existing_profile(row, *, tier_code: str) -> None:  # noqa: ANN001
    expected_template = {"entitlements": _legacy_template()}
    expected_hash = _expected_hash(tier_code)
    if (
        not bool(row.is_active)
        or row.entitlement_template_json != expected_template
        or str(row.deterministic_hash) != expected_hash
    ):
        raise RuntimeError(
            f"Legacy tier profile {tier_code!r} version 1 exists but is not immutable catalog truth"
        )


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

    existing_by_code: dict[str, object] = {}
    for tier_code in _PROFILE_DEFINITIONS:
        row = connection.execute(
            sa.select(tier_profiles).where(
                tier_profiles.c.tier_code == tier_code,
                tier_profiles.c.version == 1,
            )
        ).mappings().one_or_none()
        if row is not None:
            _validate_existing_profile(row, tier_code=tier_code)
            existing_by_code[tier_code] = row

    missing_codes = [code for code in _PROFILE_DEFINITIONS if code not in existing_by_code]
    for tier_code in missing_codes:
        definition = _PROFILE_DEFINITIONS[tier_code]
        preferred_id = str(definition["id"])
        expected_hash = _expected_hash(tier_code)
        id_owner = connection.execute(
            sa.select(tier_profiles.c.tier_code, tier_profiles.c.version).where(
                tier_profiles.c.id == preferred_id
            )
        ).first()
        if id_owner is not None:
            raise RuntimeError(
                f"Cannot restore legacy tier profile {tier_code!r}; its canonical ID is already used"
            )
        hash_owner = connection.execute(
            sa.select(tier_profiles.c.tier_code, tier_profiles.c.version).where(
                tier_profiles.c.deterministic_hash == expected_hash
            )
        ).first()
        if hash_owner is not None:
            raise RuntimeError(
                f"Cannot restore legacy tier profile {tier_code!r}; its catalog hash is already used"
            )

    for tier_code in missing_codes:
        definition = _PROFILE_DEFINITIONS[tier_code]
        connection.execute(
            tier_profiles.insert().values(
                id=str(definition["id"]),
                tier_code=tier_code,
                display_name=str(definition["display_name"]),
                version=1,
                entitlement_template_json={"entitlements": _legacy_template()},
                deterministic_hash=_expected_hash(tier_code),
                is_active=True,
                created_at=now,
                updated_at=now,
            )
        )


def downgrade() -> None:
    # These profiles can be referenced by organizations after this repair.
    # Removing immutable catalog rows on rollback would break those pointers.
    pass
