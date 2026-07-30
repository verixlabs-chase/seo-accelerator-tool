from __future__ import annotations

import uuid

import pytest
from sqlalchemy import insert, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.db.session import set_session_security_context
from app.models.campaign import Campaign
from app.models.user import User
from scripts.verify_restore_integrity import _rls_behavior_probe
from tests.conftest import create_test_campaign


pytestmark = pytest.mark.postgres_required


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
