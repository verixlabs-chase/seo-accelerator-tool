from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, insert, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.db.session import set_session_security_context
from app.models.automation_webhook import (
    AutomationWebhookConnection,
    AutomationWebhookDelivery,
    AutomationWebhookDeliveryAttempt,
)
from app.models.automation_command import (
    AutomationCommandReceipt,
    AutomationServiceAccount,
)
from app.models.business_location import BusinessLocation
from app.models.campaign import Campaign
from app.models.tier_profile import TierProfile
from app.models.user import User
from scripts.verify_restore_integrity import _rls_behavior_probe
from tests.conftest import create_test_campaign


pytestmark = pytest.mark.postgres_required


def test_application_role_can_read_immutable_tier_profile_catalog(
    db_session: Session,
) -> None:
    user = db_session.query(User).filter(User.email == "a@example.com").one()
    db_session.commit()

    isolated = Session(bind=db_session.get_bind(), autoflush=False, autocommit=False)
    try:
        set_session_security_context(
            isolated,
            tenant_id=user.tenant_id,
            organization_id=user.tenant_id,
            user_id=user.id,
            platform_access=False,
        )
        visible_profiles = set(
            isolated.execute(
                select(TierProfile.tier_code).where(TierProfile.version == 1)
            ).scalars()
        )
        assert "standard" in visible_profiles
    finally:
        isolated.rollback()
        isolated.close()


def test_rls_blocks_cross_organization_reads_and_writes(db_session: Session) -> None:
    user_a = db_session.query(User).filter(User.email == "a@example.com").one()
    user_b = db_session.query(User).filter(User.email == "b@example.com").one()
    campaign_a = create_test_campaign(
        db_session,
        user_a.tenant_id,
        tenant_id=user_a.tenant_id,
        name="RLS Campaign A",
        domain="rls-a.example",
    )
    campaign_b = create_test_campaign(
        db_session,
        user_b.tenant_id,
        tenant_id=user_b.tenant_id,
        name="RLS Campaign B",
        domain="rls-b.example",
    )
    db_session.commit()

    isolated = Session(bind=db_session.get_bind(), autoflush=False, autocommit=False)
    try:
        set_session_security_context(
            isolated,
            tenant_id=user_a.tenant_id,
            organization_id=user_a.tenant_id,
            user_id=user_a.id,
            platform_access=False,
        )
        visible_ids = set(
            isolated.execute(
                select(Campaign.id).where(Campaign.id.in_([campaign_a.id, campaign_b.id]))
            ).scalars()
        )
        assert visible_ids == {campaign_a.id}

        cross_tenant_update = isolated.execute(
            update(Campaign)
            .where(Campaign.id == campaign_b.id)
            .values(name="Cross-tenant update must not happen")
        )
        assert cross_tenant_update.rowcount == 0

        with pytest.raises(DBAPIError):
            isolated.execute(
                insert(Campaign).values(
                    id=str(uuid.uuid4()),
                    tenant_id=user_b.tenant_id,
                    organization_id=user_b.tenant_id,
                    name="Cross-tenant insert must fail",
                    domain="blocked.example",
                    month_number=1,
                    setup_state="Draft",
                    manual_automation_lock=False,
                )
            )
            isolated.flush()
    finally:
        isolated.rollback()
        isolated.close()


def test_platform_context_can_inspect_multiple_organizations(db_session: Session) -> None:
    user_a = db_session.query(User).filter(User.email == "platform-admin@example.com").one()
    tenant_ids = {
        row[0]
        for row in db_session.query(User.tenant_id)
        .filter(User.email.in_(["a@example.com", "b@example.com"]))
        .all()
    }
    for index, tenant_id in enumerate(sorted(tenant_ids)):
        create_test_campaign(
            db_session,
            tenant_id,
            tenant_id=tenant_id,
            name=f"Platform-visible {index}",
            domain=f"platform-visible-{index}.example",
        )
    db_session.commit()

    platform_session = Session(bind=db_session.get_bind(), autoflush=False, autocommit=False)
    try:
        set_session_security_context(
            platform_session,
            tenant_id=user_a.tenant_id,
            organization_id=user_a.tenant_id,
            user_id=user_a.id,
            platform_access=True,
        )
        visible_tenants = set(
            platform_session.execute(
                select(Campaign.tenant_id).where(Campaign.tenant_id.in_(tenant_ids))
            ).scalars()
        )
        assert visible_tenants == tenant_ids
    finally:
        platform_session.rollback()
        platform_session.close()


def test_inbound_automation_credentials_are_scoped_and_receipts_are_immutable(
    db_session: Session,
) -> None:
    user_a = db_session.query(User).filter(User.email == "a@example.com").one()
    user_b = db_session.query(User).filter(User.email == "b@example.com").one()
    now = datetime.now(UTC)
    rows: list[tuple[AutomationServiceAccount, AutomationCommandReceipt]] = []
    for index, user in enumerate((user_a, user_b), start=1):
        location = BusinessLocation(
            id=str(uuid.uuid4()),
            organization_id=str(user.tenant_id),
            name=f"Inbound automation location {index}",
            domain=f"inbound-automation-{index}.example",
            status="active",
            created_at=now,
            updated_at=now,
        )
        db_session.add(location)
        db_session.flush()
        account = AutomationServiceAccount(
            tenant_id=str(user.tenant_id),
            organization_id=str(user.tenant_id),
            business_location_id=location.id,
            name=f"n8n report helper {index}",
            status="active",
            token_hash=str(index) * 64,
            token_hint=f"key{index:05d}",
            token_version=1,
            allowed_commands_json='["report.retrieve"]',
            expires_at=now + timedelta(days=30),
            created_by_user_id=user.id,
            created_at=now,
            updated_at=now,
        )
        db_session.add(account)
        db_session.flush()
        receipt = AutomationCommandReceipt(
            tenant_id=str(user.tenant_id),
            organization_id=str(user.tenant_id),
            service_account_id=account.id,
            business_location_id=location.id,
            campaign_id=None,
            report_id=str(uuid.uuid4()),
            schema_version="insightos.automation.command.v1",
            command_type="report.retrieve",
            idempotency_key=f"security-inbound-report-{index}",
            correlation_id=f"security-inbound-run-{index}",
            reason="Security isolation fixture",
            request_hash="a" * 64,
            status="denied",
            denial_reason_code="automation_report_not_found",
            result_json='{"artifacts":[],"resource":null}',
            artifact_hash=str(index + 2) * 64,
            created_at=now,
            completed_at=now,
        )
        db_session.add(receipt)
        rows.append((account, receipt))
    db_session.commit()

    isolated = Session(bind=db_session.get_bind(), autoflush=False, autocommit=False)
    try:
        set_session_security_context(
            isolated,
            tenant_id=str(user_a.tenant_id),
            organization_id=str(user_a.tenant_id),
            user_id=user_a.id,
            platform_access=False,
        )
        assert set(
            isolated.execute(
                select(AutomationServiceAccount.id).where(
                    AutomationServiceAccount.id.in_([rows[0][0].id, rows[1][0].id])
                )
            ).scalars()
        ) == {rows[0][0].id}
        assert set(
            isolated.execute(
                select(AutomationCommandReceipt.id).where(
                    AutomationCommandReceipt.id.in_([rows[0][1].id, rows[1][1].id])
                )
            ).scalars()
        ) == {rows[0][1].id}
        cross_update = isolated.execute(
            update(AutomationServiceAccount)
            .where(AutomationServiceAccount.id == rows[1][0].id)
            .values(name="Cross-tenant key")
        )
        assert cross_update.rowcount == 0
    finally:
        isolated.rollback()
        isolated.close()

    immutable = Session(bind=db_session.get_bind(), autoflush=False, autocommit=False)
    try:
        set_session_security_context(
            immutable,
            tenant_id=str(user_a.tenant_id),
            organization_id=str(user_a.tenant_id),
            user_id=user_a.id,
            platform_access=False,
        )
        with pytest.raises(DBAPIError):
            immutable.execute(
                update(AutomationCommandReceipt)
                .where(AutomationCommandReceipt.id == rows[0][1].id)
                .values(status="succeeded")
            )
            immutable.flush()
    finally:
        immutable.rollback()
        immutable.close()

    undeletable = Session(bind=db_session.get_bind(), autoflush=False, autocommit=False)
    try:
        set_session_security_context(
            undeletable,
            tenant_id=str(user_a.tenant_id),
            organization_id=str(user_a.tenant_id),
            user_id=user_a.id,
            platform_access=False,
        )
        with pytest.raises(DBAPIError):
            undeletable.execute(
                delete(AutomationCommandReceipt).where(
                    AutomationCommandReceipt.id == rows[0][1].id
                )
            )
            undeletable.flush()
    finally:
        undeletable.rollback()
        undeletable.close()


def test_restore_verifier_rls_probe_is_non_persistent(db_session: Session) -> None:
    before_count = db_session.query(Campaign).count()
    db_session.commit()

    with db_session.get_bind().begin() as connection:
        result = _rls_behavior_probe(connection)

    db_session.expire_all()
    assert result == {
        "passed": True,
        "visible_own_campaign": True,
        "visible_cross_tenant_campaign": False,
        "cross_tenant_update_rows": 0,
        "cross_tenant_insert_blocked": True,
        "persisted_rows": False,
    }
    assert db_session.query(Campaign).count() == before_count


def test_automation_webhook_rows_are_scoped_and_attempts_are_append_only(
    db_session: Session,
) -> None:
    user_a = db_session.query(User).filter(User.email == "a@example.com").one()
    user_b = db_session.query(User).filter(User.email == "b@example.com").one()
    now = datetime.now(UTC)

    def _rows(user: User, suffix: str):
        connection = AutomationWebhookConnection(
            id=str(uuid.uuid4()),
            tenant_id=user.tenant_id,
            organization_id=user.tenant_id,
            name=f"RLS workflow {suffix}",
            provider="zapier",
            status="active",
            endpoint_host="hooks.zapier.com",
            event_types_json='["report.ready"]',
            encrypted_config_blob=f"encrypted-{suffix}",
            signing_secret_version=1,
            verification_status="verified",
            consecutive_failures=0,
            created_by_user_id=user.id,
            created_at=now,
            updated_at=now,
        )
        delivery = AutomationWebhookDelivery(
            id=str(uuid.uuid4()),
            tenant_id=user.tenant_id,
            organization_id=user.tenant_id,
            connection_id=connection.id,
            event_id=f"evt_rls_{suffix}",
            event_type="report.ready",
            schema_version="insightos.automation.event.v1",
            status="failed",
            encrypted_event_blob=f"event-{suffix}",
            event_hash=("a" if suffix == "a" else "b") * 64,
            attempt_count=1,
            max_attempts=3,
            created_by_user_id=user.id,
            created_at=now,
            updated_at=now,
        )
        attempt = AutomationWebhookDeliveryAttempt(
            id=str(uuid.uuid4()),
            tenant_id=user.tenant_id,
            organization_id=user.tenant_id,
            delivery_id=delivery.id,
            attempt_number=1,
            status="failed",
            reason_code="automation_destination_unreachable",
            duration_ms=5,
            attempted_at=now,
        )
        return connection, delivery, attempt

    connection_a, delivery_a, attempt_a = _rows(user_a, "a")
    connection_b, delivery_b, attempt_b = _rows(user_b, "b")
    db_session.add_all(
        [connection_a, delivery_a, attempt_a, connection_b, delivery_b, attempt_b]
    )
    db_session.commit()

    isolated = Session(bind=db_session.get_bind(), autoflush=False, autocommit=False)
    try:
        set_session_security_context(
            isolated,
            tenant_id=user_a.tenant_id,
            organization_id=user_a.tenant_id,
            user_id=user_a.id,
            platform_access=False,
        )
        assert set(isolated.execute(select(AutomationWebhookConnection.id)).scalars()) == {
            connection_a.id
        }
        assert set(isolated.execute(select(AutomationWebhookDelivery.id)).scalars()) == {
            delivery_a.id
        }
        assert set(
            isolated.execute(select(AutomationWebhookDeliveryAttempt.id)).scalars()
        ) == {attempt_a.id}
        cross_scope = isolated.execute(
            update(AutomationWebhookConnection)
            .where(AutomationWebhookConnection.id == connection_b.id)
            .values(status="unhealthy")
        )
        assert cross_scope.rowcount == 0
        with pytest.raises(DBAPIError):
            isolated.execute(
                update(AutomationWebhookDeliveryAttempt)
                .where(AutomationWebhookDeliveryAttempt.id == attempt_a.id)
                .values(reason_code="changed")
            )
            isolated.flush()
    finally:
        isolated.rollback()
        isolated.close()
