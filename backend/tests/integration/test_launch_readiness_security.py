from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.db.session import set_session_security_context
from app.models.launch_readiness import LaunchReadinessDecision, LaunchReadinessProof
from app.models.user import User


pytestmark = pytest.mark.postgres_required


def _proof(*, user_id: str) -> LaunchReadinessProof:
    now = datetime.now(UTC)
    return LaunchReadinessProof(
        schema_version="ops1-launch-proof-v1",
        gate_code="critical_journeys",
        result="passed",
        proof_kind="production_smoke",
        summary="The current production customer journey completed with saved evidence.",
        evidence_reference=f"PG-READINESS-{uuid.uuid4().hex[:12]}",
        evidence_digest=uuid.uuid4().hex * 2,
        recorded_by_user_id=user_id,
        observed_at=now,
        expires_at=now + timedelta(days=30),
        created_at=now,
    )


def _decision(*, user_id: str) -> LaunchReadinessDecision:
    return LaunchReadinessDecision(
        schema_version="ops1-launch-decision-v1",
        decision="no_go",
        basis_digest=uuid.uuid4().hex * 2,
        release_reference=f"PG-DECISION-{uuid.uuid4().hex[:12]}",
        rationale="The saved evidence still contains a launch blocker.",
        known_limitations_acknowledged=False,
        support_owner_confirmed=False,
        rollback_owner_confirmed=False,
        evidence_current_confirmed=True,
        decision_digest=uuid.uuid4().hex * 2,
        decided_by_user_id=user_id,
        created_at=datetime.now(UTC),
    )


def test_launch_proof_is_platform_only_and_database_immutable(db_session: Session) -> None:
    user = db_session.query(User).filter(User.email == "a@example.com").one()
    db_session.commit()
    bind = db_session.get_bind()

    tenant_session = Session(bind=bind, autoflush=False, autocommit=False)
    try:
        set_session_security_context(
            tenant_session,
            tenant_id=user.tenant_id,
            organization_id=user.tenant_id,
            user_id=user.id,
            platform_access=False,
        )
        assert tenant_session.execute(select(LaunchReadinessProof.id)).scalars().all() == []
        assert tenant_session.execute(select(LaunchReadinessDecision.id)).scalars().all() == []
        tenant_session.add(_proof(user_id=user.id))
        with pytest.raises(DBAPIError):
            tenant_session.flush()
    finally:
        tenant_session.rollback()
        tenant_session.close()

    platform_session = Session(bind=bind, autoflush=False, autocommit=False)
    try:
        set_session_security_context(
            platform_session,
            tenant_id=user.tenant_id,
            organization_id=user.tenant_id,
            user_id=user.id,
            platform_access=True,
        )
        proof = _proof(user_id=user.id)
        decision = _decision(user_id=user.id)
        platform_session.add_all([proof, decision])
        platform_session.commit()
        proof_id = proof.id
        decision_id = decision.id
    finally:
        platform_session.close()

    update_session = Session(bind=bind, autoflush=False, autocommit=False)
    try:
        set_session_security_context(
            update_session,
            tenant_id=user.tenant_id,
            organization_id=user.tenant_id,
            user_id=user.id,
            platform_access=True,
        )
        visible = update_session.execute(
            select(LaunchReadinessProof.id).where(LaunchReadinessProof.id == proof_id)
        ).scalar_one()
        assert visible == proof_id
        with pytest.raises(DBAPIError):
            update_session.execute(
                update(LaunchReadinessProof)
                .where(LaunchReadinessProof.id == proof_id)
                .values(result="failed")
            )
    finally:
        update_session.rollback()
        update_session.close()

    decision_update_session = Session(bind=bind, autoflush=False, autocommit=False)
    try:
        set_session_security_context(
            decision_update_session,
            tenant_id=user.tenant_id,
            organization_id=user.tenant_id,
            user_id=user.id,
            platform_access=True,
        )
        visible_decision = decision_update_session.execute(
            select(LaunchReadinessDecision.id).where(
                LaunchReadinessDecision.id == decision_id
            )
        ).scalar_one()
        assert visible_decision == decision_id
        with pytest.raises(DBAPIError):
            decision_update_session.execute(
                update(LaunchReadinessDecision)
                .where(LaunchReadinessDecision.id == decision_id)
                .values(decision="go")
            )
    finally:
        decision_update_session.rollback()
        decision_update_session.close()
