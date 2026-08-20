from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.db.session import set_session_security_context
from app.models.production_capability import ProductionCapabilityProof
from app.models.user import User


pytestmark = pytest.mark.postgres_required


def _proof(*, user_id: str) -> ProductionCapabilityProof:
    now = datetime.now(UTC)
    return ProductionCapabilityProof(
        schema_version="ops1-capability-proof-v1",
        capability_code="guided_search_plan",
        result="proven",
        summary="The current production journey completed with the expected customer result.",
        customer_limitation=None,
        evidence_reference=f"PG-CAPABILITY-{uuid.uuid4().hex[:12]}",
        evidence_digest=uuid.uuid4().hex * 2,
        recorded_by_user_id=user_id,
        observed_at=now,
        expires_at=now + timedelta(days=30),
        created_at=now,
    )


def test_production_capability_proof_is_platform_only_and_immutable(
    db_session: Session,
) -> None:
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
        assert tenant_session.execute(
            select(ProductionCapabilityProof.id)
        ).scalars().all() == []
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
        platform_session.add(proof)
        platform_session.commit()
        proof_id = proof.id
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
        assert update_session.execute(
            select(ProductionCapabilityProof.id).where(
                ProductionCapabilityProof.id == proof_id
            )
        ).scalar_one() == proof_id
        with pytest.raises(DBAPIError):
            update_session.execute(
                update(ProductionCapabilityProof)
                .where(ProductionCapabilityProof.id == proof_id)
                .values(result="unavailable")
            )
    finally:
        update_session.rollback()
        update_session.close()
