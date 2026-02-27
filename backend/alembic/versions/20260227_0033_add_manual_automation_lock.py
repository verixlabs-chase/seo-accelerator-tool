"""add manual_automation_lock to campaigns (SQLite-safe)"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260227_0033"
down_revision = "20260227_0032"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    dialect = bind.dialect.name

    # Add column with temporary default (SQLite requires a default for non-nullable)
    op.add_column(
        "campaigns",
        sa.Column(
            "manual_automation_lock",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )

    # Drop default in dialect-safe way
    if dialect == "sqlite":
        with op.batch_alter_table("campaigns") as batch_op:
            batch_op.alter_column(
                "manual_automation_lock",
                server_default=None,
            )
    else:
        op.alter_column(
            "campaigns",
            "manual_automation_lock",
            server_default=None,
        )


def downgrade():
    op.drop_column("campaigns", "manual_automation_lock")