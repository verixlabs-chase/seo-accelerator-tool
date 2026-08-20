from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.db.session import set_session_security_context
from app.models.customer_status import CustomerStatusUpdate
from app.models.user import User


pytestmark = pytest.mark.postgres_required


def _status(*, user_id: str, visible: bool, suffix: str) -> CustomerStatusUpdate:
    now = datetime.now(UTC)
    return CustomerStatusUpdate(
        schema_version="ops1-customer-status-v1",
        incident_key=f"pg-status-{suffix}",
        update_number=1,
        state="investigating",
        impact="minor",
        title="Some reports are taking longer",
        message="We are working to restore normal report delivery. Saved work is not affected.",
        affected_surfaces=["reports"],
        visible_to_customers=visible,
        starts_at=now,
        ends_at=None,
        content_digest=uuid.uuid4().hex * 2,
        created_by_user_id=user_id,
        created_at=now,
    )


def test_customer_status_is_globally_readable_only_when_visible_and_always_immutable(
    db_session: Session,
) -> None:
    user = db_session.query(User).filter(User.email == "a@example.com").one()
    db_session.commit()
    bind = db_session.get_bind()

    platform_session = Session(bind=bind, autoflush=False, autocommit=False)
    try:
        set_session_security_context(
            platform_session,
            tenant_id=user.tenant_id,
            organization_id=user.tenant_id,
            user_id=user.id,
            platform_access=True,
        )
        visible = _status(user_id=user.id, visible=True, suffix=uuid.uuid4().hex[:8])
        hidden = _status(user_id=user.id, visible=False, suffix=uuid.uuid4().hex[:8])
        platform_session.add_all([visible, hidden])
        platform_session.commit()
        visible_id = visible.id
        hidden_id = hidden.id
    finally:
        platform_session.close()

    tenant_session = Session(bind=bind, autoflush=False, autocommit=False)
    try:
        set_session_security_context(
            tenant_session,
            tenant_id=user.tenant_id,
            organization_id=user.tenant_id,
            user_id=user.id,
            platform_access=False,
        )
        visible_ids = set(
            tenant_session.execute(select(CustomerStatusUpdate.id)).scalars().all()
        )
        assert visible_id in visible_ids
        assert hidden_id not in visible_ids
        tenant_session.add(
            _status(user_id=user.id, visible=True, suffix=uuid.uuid4().hex[:8])
        )
        with pytest.raises(DBAPIError):
            tenant_session.flush()
    finally:
        tenant_session.rollback()
        tenant_session.close()

    update_session = Session(bind=bind, autoflush=False, autocommit=False)
    try:
        set_session_security_context(
            update_session,
            tenant_id=user.tenant_id,
            organization_id=user.tenant_id,
            user_id=user.id,
            platform_access=True,
        )
        with pytest.raises(DBAPIError):
            update_session.execute(
                update(CustomerStatusUpdate)
                .where(CustomerStatusUpdate.id == visible_id)
                .values(message="This history must remain unchanged.")
            )
    finally:
        update_session.rollback()
        update_session.close()
