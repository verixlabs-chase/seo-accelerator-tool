from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.db.session import set_session_security_context
from app.models.launch_experience import LaunchExperienceReview
from app.models.user import User


pytestmark = pytest.mark.postgres_required


def _review(*, user_id: str) -> LaunchExperienceReview:
    now = datetime.now(UTC)
    return LaunchExperienceReview(
        schema_version="ops1-experience-review-v1",
        review_kind="route_audit",
        subject_code="overview",
        viewport="desktop",
        result="passed",
        session_reference=None,
        summary="The route was understandable and recoverable in the tested viewport.",
        issue_count=0,
        blocking_issue_count=0,
        evidence_reference=f"PG-EXPERIENCE-{uuid.uuid4().hex[:12]}",
        evidence_digest=uuid.uuid4().hex * 2,
        recorded_by_user_id=user_id,
        observed_at=now,
        expires_at=now + timedelta(days=30),
        created_at=now,
    )


def test_launch_experience_review_is_platform_only_and_immutable(db_session: Session) -> None:
    user = db_session.query(User).filter(User.email == "a@example.com").one()
    db_session.commit()
    bind = db_session.get_bind()

    tenant = Session(bind=bind, autoflush=False, autocommit=False)
    try:
        set_session_security_context(
            tenant,
            tenant_id=user.tenant_id,
            organization_id=user.tenant_id,
            user_id=user.id,
            platform_access=False,
        )
        assert tenant.execute(select(LaunchExperienceReview.id)).scalars().all() == []
        tenant.add(_review(user_id=user.id))
        with pytest.raises(DBAPIError):
            tenant.flush()
    finally:
        tenant.rollback()
        tenant.close()

    platform = Session(bind=bind, autoflush=False, autocommit=False)
    try:
        set_session_security_context(
            platform,
            tenant_id=user.tenant_id,
            organization_id=user.tenant_id,
            user_id=user.id,
            platform_access=True,
        )
        row = _review(user_id=user.id)
        platform.add(row)
        platform.commit()
        review_id = row.id
    finally:
        platform.close()

    mutation = Session(bind=bind, autoflush=False, autocommit=False)
    try:
        set_session_security_context(
            mutation,
            tenant_id=user.tenant_id,
            organization_id=user.tenant_id,
            user_id=user.id,
            platform_access=True,
        )
        assert mutation.execute(
            select(LaunchExperienceReview.id).where(LaunchExperienceReview.id == review_id)
        ).scalar_one() == review_id
        with pytest.raises(DBAPIError):
            mutation.execute(
                update(LaunchExperienceReview)
                .where(LaunchExperienceReview.id == review_id)
                .values(result="failed")
            )
    finally:
        mutation.rollback()
        mutation.close()
