"""add governed performance drift events

Revision ID: 20260810_0105
Revises: 20260809_0104
Create Date: 2026-08-10 13:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260810_0105"
down_revision = "20260809_0104"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "performance_drift_events",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("detector_version", sa.String(40), nullable=False),
        sa.Column("label", sa.String(40), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="needs_review"),
        sa.Column("provider_name", sa.String(100), nullable=False),
        sa.Column("metric_family", sa.String(100), nullable=False),
        sa.Column("metric_contract_id", sa.String(180), nullable=False),
        sa.Column("metric_contract_version", sa.String(40), nullable=False),
        sa.Column("comparison_scope_hash", sa.String(64), nullable=False),
        sa.Column("baseline_start", sa.Date(), nullable=False),
        sa.Column("baseline_end", sa.Date(), nullable=False),
        sa.Column("comparison_start", sa.Date(), nullable=False),
        sa.Column("comparison_end", sa.Date(), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("organization_count", sa.Integer(), nullable=False),
        sa.Column("excluded_sample_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("direction", sa.String(12), nullable=False),
        sa.Column("median_change", sa.Float(), nullable=False),
        sa.Column("confidence_low", sa.Float(), nullable=False),
        sa.Column("confidence_high", sa.Float(), nullable=False),
        sa.Column("agreement_ratio", sa.Float(), nullable=False),
        sa.Column("cohort_rules", sa.JSON(), nullable=False),
        sa.Column("known_confounders", sa.JSON(), nullable=False),
        sa.Column("affected_metric_families", sa.JSON(), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("plain_language_summary", sa.Text(), nullable=False),
        sa.Column("investigation_note", sa.Text(), nullable=True),
        sa.Column("reviewed_by_user_id", sa.String(36), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "automatic_activation_allowed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "label in ('possible_ecosystem_change','unusual_shared_movement')",
            name="ck_performance_drift_events_label",
        ),
        sa.CheckConstraint(
            "direction in ('up','down')",
            name="ck_performance_drift_events_direction",
        ),
        sa.CheckConstraint(
            "status in ('needs_review','investigating','dismissed','resolved')",
            name="ck_performance_drift_events_status",
        ),
        sa.CheckConstraint(
            "sample_size >= 0 and organization_count >= 0",
            name="ck_performance_drift_events_sample_counts",
        ),
        sa.UniqueConstraint(
            "detector_version",
            "metric_contract_id",
            "comparison_scope_hash",
            "comparison_end",
            "evidence_digest",
            name="uq_performance_drift_events_detector_evidence",
        ),
    )
    for name, columns in (
        ("ix_performance_drift_events_label", ["label"]),
        ("ix_performance_drift_events_status", ["status"]),
        ("ix_performance_drift_events_provider_name", ["provider_name"]),
        ("ix_performance_drift_events_metric_family", ["metric_family"]),
        ("ix_performance_drift_events_metric_contract_id", ["metric_contract_id"]),
        ("ix_performance_drift_events_comparison_end", ["comparison_end"]),
        ("ix_performance_drift_events_created_at", ["created_at"]),
        ("ix_performance_drift_events_status_created", ["status", "created_at"]),
        (
            "ix_performance_drift_events_contract_period",
            ["metric_contract_id", "comparison_end"],
        ),
    ):
        op.create_index(name, "performance_drift_events", columns)


def downgrade() -> None:
    op.drop_table("performance_drift_events")
