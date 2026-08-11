"""tenant-scope the durable event outbox

Revision ID: 20260811_0118
Revises: 20260811_0117
Create Date: 2026-08-11 19:00:00.000000
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa


revision = "20260811_0118"
down_revision = "20260811_0117"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("event_outbox") as batch:
        batch.add_column(sa.Column("tenant_id", sa.String(36), nullable=True))

    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, payload_json FROM event_outbox WHERE tenant_id IS NULL")
    ).mappings()
    for row in rows:
        tenant_id = "legacy-unscoped"
        try:
            payload = json.loads(str(row["payload_json"] or "{}"))
            candidate = str(payload.get("tenant_id") or "").strip()
            if candidate:
                tenant_id = candidate[:36]
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
        bind.execute(
            sa.text(
                "UPDATE event_outbox SET tenant_id = :tenant_id WHERE id = :event_id"
            ),
            {"tenant_id": tenant_id, "event_id": row["id"]},
        )

    with op.batch_alter_table("event_outbox") as batch:
        batch.alter_column(
            "tenant_id",
            existing_type=sa.String(36),
            nullable=False,
        )
        batch.create_index("ix_event_outbox_tenant_id", ["tenant_id"], unique=False)

    if bind.dialect.name == "postgresql":
        op.execute(
            sa.text(
                "GRANT SELECT, INSERT, UPDATE, DELETE "
                "ON TABLE public.event_outbox TO lsos_app"
            )
        )
        op.execute(sa.text("ALTER TABLE public.event_outbox ENABLE ROW LEVEL SECURITY"))
        op.execute(
            sa.text(
                "DROP POLICY IF EXISTS lsos_tenant_isolation "
                "ON public.event_outbox"
            )
        )
        op.execute(
            sa.text(
                "CREATE POLICY lsos_tenant_isolation ON public.event_outbox "
                "FOR ALL TO lsos_app "
                "USING (current_setting('app.platform_access', true) = 'on' OR "
                "tenant_id::text = current_setting('app.current_tenant_id', true)) "
                "WITH CHECK (current_setting('app.platform_access', true) = 'on' OR "
                "tenant_id::text = current_setting('app.current_tenant_id', true))"
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            sa.text(
                "DROP POLICY IF EXISTS lsos_tenant_isolation "
                "ON public.event_outbox"
            )
        )
        op.execute(sa.text("ALTER TABLE public.event_outbox DISABLE ROW LEVEL SECURITY"))

    with op.batch_alter_table("event_outbox") as batch:
        batch.drop_index("ix_event_outbox_tenant_id")
        batch.drop_column("tenant_id")
