"""add organization provider credential policy foundation

Revision ID: 20260219_0018
Revises: 20260219_0017
Create Date: 2026-02-19 18:20:00
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from alembic import op
import sqlalchemy as sa


revision = "20260219_0018"
down_revision = "20260219_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("plan_type", sa.String(length=30), nullable=False, server_default="standard"),
        sa.Column("billing_mode", sa.String(length=30), nullable=False, server_default="subscription"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "plan_type in ('internal_anchor','standard','enterprise')",
            name="ck_organizations_plan_type",
        ),
        sa.CheckConstraint(
            "billing_mode in ('platform_sponsored','subscription','custom_contract')",
            name="ck_organizations_billing_mode",
        ),
        sa.UniqueConstraint("name", name="uq_organizations_name"),
    )
    op.create_index("ix_organizations_plan_type", "organizations", ["plan_type"])
    op.create_index("ix_organizations_billing_mode", "organizations", ["billing_mode"])

    op.create_table(
        "provider_policies",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.String(length=36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider_name", sa.String(length=80), nullable=False),
        sa.Column("credential_mode", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "credential_mode in ('platform','byo_optional','byo_required')",
            name="ck_provider_policies_credential_mode",
        ),
        sa.UniqueConstraint("organization_id", "provider_name", name="uq_provider_policies_org_provider"),
    )
    op.create_index("ix_provider_policies_organization_id", "provider_policies", ["organization_id"])

    op.create_table(
        "organization_provider_credentials",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.String(length=36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider_name", sa.String(length=80), nullable=False),
        sa.Column("auth_mode", sa.String(length=20), nullable=False),
        sa.Column("encrypted_secret_blob", sa.Text(), nullable=False),
        sa.Column("key_reference", sa.String(length=120), nullable=False),
        sa.Column("key_version", sa.String(length=40), nullable=False, server_default="v1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "auth_mode in ('api_key','basic','oauth2')",
            name="ck_org_provider_credentials_auth_mode",
        ),
        sa.UniqueConstraint("organization_id", "provider_name", name="uq_org_provider_credentials_org_provider"),
    )
    op.create_index(
        "ix_organization_provider_credentials_organization_id",
        "organization_provider_credentials",
        ["organization_id"],
    )

    op.create_table(
        "platform_provider_credentials",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("provider_name", sa.String(length=80), nullable=False),
        sa.Column("auth_mode", sa.String(length=20), nullable=False),
        sa.Column("encrypted_secret_blob", sa.Text(), nullable=False),
        sa.Column("key_reference", sa.String(length=120), nullable=False),
        sa.Column("key_version", sa.String(length=40), nullable=False, server_default="v1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "auth_mode in ('api_key','basic','oauth2')",
            name="ck_platform_provider_credentials_auth_mode",
        ),
        sa.UniqueConstraint("provider_name", name="uq_platform_provider_credentials_provider"),
    )

    _seed_internal_anchor_policy()


def downgrade() -> None:
    op.drop_table("platform_provider_credentials")
    op.drop_index(
        "ix_organization_provider_credentials_organization_id",
        table_name="organization_provider_credentials",
    )
    op.drop_table("organization_provider_credentials")
    op.drop_index("ix_provider_policies_organization_id", table_name="provider_policies")
    op.drop_table("provider_policies")
    op.drop_index("ix_organizations_billing_mode", table_name="organizations")
    op.drop_index("ix_organizations_plan_type", table_name="organizations")
    op.drop_table("organizations")


def _seed_internal_anchor_policy() -> None:
    now = datetime.now(UTC)
    conn = op.get_bind()
    organizations = sa.table(
        "organizations",
        sa.column("id", sa.String(length=36)),
        sa.column("name", sa.String(length=255)),
        sa.column("plan_type", sa.String(length=30)),
        sa.column("billing_mode", sa.String(length=30)),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    provider_policies = sa.table(
        "provider_policies",
        sa.column("id", sa.String(length=36)),
        sa.column("organization_id", sa.String(length=36)),
        sa.column("provider_name", sa.String(length=80)),
        sa.column("credential_mode", sa.String(length=20)),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )

    internal_anchor_org = conn.execute(
        sa.select(organizations.c.id)
        .where(
            organizations.c.plan_type == "enterprise",
            organizations.c.billing_mode == "platform_sponsored",
        )
        .limit(1)
    ).first()

    if internal_anchor_org is None:
        org_id = str(uuid.uuid4())
        conn.execute(
            organizations.insert().values(
                id=org_id,
                name="internal_anchor_enterprise_seed",
                plan_type="enterprise",
                billing_mode="platform_sponsored",
                created_at=now,
                updated_at=now,
            )
        )
    else:
        org_id = str(internal_anchor_org[0])
        conn.execute(
            organizations.update()
            .where(organizations.c.id == org_id)
            .values(
                plan_type="enterprise",
                billing_mode="platform_sponsored",
                updated_at=now,
            )
        )

    policy = conn.execute(
        sa.select(provider_policies.c.id).where(
            provider_policies.c.organization_id == org_id,
            provider_policies.c.provider_name == "dataforseo",
        )
    ).first()
    if policy is None:
        conn.execute(
            provider_policies.insert().values(
                id=str(uuid.uuid4()),
                organization_id=org_id,
                provider_name="dataforseo",
                credential_mode="byo_required",
                created_at=now,
                updated_at=now,
            )
        )
    else:
        conn.execute(
            provider_policies.update()
            .where(provider_policies.c.id == str(policy[0]))
            .values(credential_mode="byo_required", updated_at=now)
        )
