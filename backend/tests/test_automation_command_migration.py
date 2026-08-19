from __future__ import annotations

from pathlib import Path

from sqlalchemy import inspect

from app.models.automation_command import (
    AutomationCommandReceipt,
    AutomationServiceAccount,
    AutomationServiceAccountLocation,
)


MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260819_0188_inbound_automation_service_accounts.py"
)
EXPANSION_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260819_0189_saved_report_generation_command.py"
)
RECOMMENDATION_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260819_0190_saved_recommendation_command.py"
)
REVIEW_REQUEST_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260819_0191_recommendation_review_request_command.py"
)
CONNECTION_REFRESH_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260819_0192_saved_connection_refresh_command.py"
)
PRICED_LISTING_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260819_0193_priced_public_listing_check_command.py"
)
WORKING_DRAFT_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260819_0194_governed_working_draft_command.py"
)
DRAFT_REVIEW_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260819_0195_content_draft_review_request_command.py"
)
MULTI_LOCATION_SCOPE_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260819_0196_explicit_automation_location_scopes.py"
)
SAVED_REVIEW_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260819_0197_saved_review_retrieval_command.py"
)
REVIEW_DRAFT_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260819_0198_review_response_draft_command.py"
)


def test_inbound_automation_schema_matches_models(db_session) -> None:
    inspector = inspect(db_session.get_bind())
    assert {
        AutomationServiceAccount.__tablename__,
        AutomationServiceAccountLocation.__tablename__,
        AutomationCommandReceipt.__tablename__,
    }.issubset(set(inspector.get_table_names()))

    account_columns = {
        item["name"]: item for item in inspector.get_columns("automation_service_accounts")
    }
    receipt_columns = {
        item["name"]: item for item in inspector.get_columns("automation_command_receipts")
    }
    assert {
        "tenant_id",
        "organization_id",
        "business_location_id",
        "token_hash",
        "token_hint",
        "allowed_commands_json",
        "expires_at",
        "revoked_at",
    }.issubset(account_columns)
    assert {
        "service_account_id",
        "campaign_id",
        "report_id",
        "recommendation_id",
        "command_type",
        "idempotency_key",
        "request_hash",
        "denial_reason_code",
        "result_json",
        "artifact_hash",
    }.issubset(receipt_columns)
    assert account_columns["token_hash"]["nullable"] is False
    assert receipt_columns["campaign_id"]["nullable"] is True
    assert receipt_columns["report_id"]["nullable"] is True
    assert receipt_columns["recommendation_id"]["nullable"] is True

    account_indexes = {
        item["name"] for item in inspector.get_indexes("automation_service_accounts")
    }
    receipt_indexes = {
        item["name"] for item in inspector.get_indexes("automation_command_receipts")
    }
    assert "uq_automation_service_accounts_one_active_org" in account_indexes
    assert "ix_automation_command_receipts_account_created" in receipt_indexes


def test_inbound_automation_migration_is_scoped_immutable_and_reversible() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "20260819_0188"' in source
    assert 'down_revision = "20260819_0187"' in source
    assert 'command_type in (\'report.retrieve\')' in source
    assert "uq_automation_service_accounts_one_active_org" in source
    assert "fk_automation_command_receipts_account_scope" in source
    assert "fk_automation_command_receipts_campaign_scope" in source
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "app.current_tenant_id" in source
    assert "app.current_organization_id" in source
    assert "REVOKE UPDATE, DELETE" in source
    assert "BEFORE UPDATE OR DELETE" in source
    assert "automation command receipts are immutable" in source
    assert "app.platform_maintenance" in source
    assert 'op.drop_table(RECEIPT_TABLE)' in source
    assert 'op.drop_table(ACCOUNT_TABLE)' in source


def test_saved_report_generation_migration_is_bounded_and_fail_closed() -> None:
    source = EXPANSION_MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "20260819_0189"' in source
    assert 'down_revision = "20260819_0188"' in source
    assert "'report.retrieve','report.generate_saved'" in source
    assert 'batch.alter_column("report_id"' in source
    assert "generated_receipt" in source
    assert "expanded_account" in source
    assert "Cannot downgrade" in source


def test_saved_recommendation_migration_is_scoped_and_fail_closed() -> None:
    source = RECOMMENDATION_MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "20260819_0190"' in source
    assert 'down_revision = "20260819_0189"' in source
    assert "'recommendation.retrieve'" in source
    assert "fk_automation_command_receipts_recommendation_scope" in source
    assert "uq_strategy_recommendations_id_scope" in source
    assert "Cannot downgrade" in source


def test_recommendation_review_request_migration_is_bounded() -> None:
    source = REVIEW_REQUEST_MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "20260819_0191"' in source
    assert 'down_revision = "20260819_0190"' in source
    assert "'recommendation.request_review'" in source
    assert "Cannot downgrade" in source


def test_saved_connection_refresh_migration_is_bounded() -> None:
    source = CONNECTION_REFRESH_MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "20260819_0192"' in source
    assert 'down_revision = "20260819_0191"' in source
    assert "'connection.refresh_saved'" in source
    assert "Cannot downgrade" in source


def test_priced_public_listing_check_migration_is_bounded() -> None:
    source = PRICED_LISTING_MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "20260819_0193"' in source
    assert 'down_revision = "20260819_0192"' in source
    assert "'listing.check_public'" in source
    assert "Cannot downgrade" in source


def test_governed_working_draft_migration_is_bounded() -> None:
    source = WORKING_DRAFT_MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "20260819_0194"' in source
    assert 'down_revision = "20260819_0193"' in source
    assert "'content.create_working_draft'" in source
    assert "Cannot downgrade" in source


def test_content_draft_review_request_migration_is_bounded() -> None:
    source = DRAFT_REVIEW_MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "20260819_0195"' in source
    assert 'down_revision = "20260819_0194"' in source
    assert "'content.request_draft_review'" in source
    assert "Cannot downgrade" in source


def test_multi_location_scope_migration_is_explicit_and_bounded() -> None:
    source = MULTI_LOCATION_SCOPE_MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "20260819_0196"' in source
    assert 'down_revision = "20260819_0195"' in source
    assert "automation_service_account_locations" in source
    assert "business_location_id" in source
    assert "Cannot downgrade" in source


def test_saved_review_retrieval_migration_is_bounded() -> None:
    source = SAVED_REVIEW_MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "20260819_0197"' in source
    assert 'down_revision = "20260819_0196"' in source
    assert "'review.retrieve'" in source
    assert "Cannot downgrade" in source


def test_review_response_draft_command_migration_is_bounded() -> None:
    source = REVIEW_DRAFT_MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "20260819_0198"' in source
    assert 'down_revision = "20260819_0197"' in source
    assert "'review.create_response_draft'" in source
    assert "Cannot downgrade" in source
