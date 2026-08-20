from __future__ import annotations

import base64
import threading
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

from app.db.session import set_session_security_context
from app.models.business_location import BusinessLocation
from app.models.organization import Organization
from app.models.organization_membership import OrganizationMembership
from app.models.portfolio_targeting import (
    PortfolioLocationAccessGrant,
    PortfolioLocationGroup,
    PortfolioLocationGroupMember,
)
from app.models.user import User
from app.services import enterprise_client_invitation_service
from app.services.commercial_plan_service import apply_commercial_plan


pytestmark = pytest.mark.postgres_required
MASTER_KEY_B64 = base64.b64encode(b"i" * 32).decode()


def test_postgres_client_invitation_accept_has_one_winner(
    apply_migrations,
    db_session,
    monkeypatch,
) -> None:
    monkeypatch.setenv("PLATFORM_MASTER_KEY", MASTER_KEY_B64)
    owner = db_session.query(User).filter(User.email == "org-owner@example.com").one()
    owner_membership = (
        db_session.query(OrganizationMembership)
        .filter(
            OrganizationMembership.user_id == owner.id,
            OrganizationMembership.role == "org_owner",
        )
        .one()
    )
    organization = db_session.get(Organization, owner_membership.organization_id)
    assert organization is not None
    apply_commercial_plan(db_session, organization_id=organization.id, plan_code="enterprise")
    now = datetime.now(UTC)
    location = BusinessLocation(
        id=str(uuid.uuid4()),
        organization_id=organization.id,
        name="Concurrent client location",
        domain="concurrent-client.example",
        status="active",
        created_at=now,
        updated_at=now,
    )
    group = PortfolioLocationGroup(
        id=str(uuid.uuid4()),
        tenant_id=organization.id,
        organization_id=organization.id,
        name="Concurrent client group",
        status="active",
        version=1,
        created_at=now,
        updated_at=now,
    )
    member = PortfolioLocationGroupMember(
        id=str(uuid.uuid4()),
        tenant_id=organization.id,
        organization_id=organization.id,
        location_group_id=group.id,
        business_location_id=location.id,
        added_by_user_id=owner.id,
        created_at=now,
    )
    db_session.add_all([location, group, member])
    db_session.flush()
    _item, token, _created = enterprise_client_invitation_service.create_client_invitation(
        db_session,
        tenant_id=organization.id,
        organization_id=organization.id,
        actor_user_id=owner.id,
        email="concurrent.client@example.com",
        location_group_id=group.id,
        expires_in_days=7,
    )
    db_session.commit()

    first_holds_invitation = threading.Event()
    release_first = threading.Event()
    second_done = threading.Event()
    original_active_group = enterprise_client_invitation_service._active_group

    def blocking_active_group(*args, **kwargs):
        if threading.current_thread().name == "client-invite-first":
            first_holds_invitation.set()
            if not release_first.wait(timeout=5):
                raise AssertionError("Timed out while holding the client invitation row")
        return original_active_group(*args, **kwargs)

    monkeypatch.setattr(
        enterprise_client_invitation_service,
        "_active_group",
        blocking_active_group,
    )
    engine = create_engine(str(apply_migrations["database_url"]), pool_pre_ping=True)
    session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    results: dict[str, dict[str, str]] = {}
    errors: dict[str, BaseException] = {}

    def accept(name: str, *, done: threading.Event | None = None) -> None:
        session = session_local()
        try:
            set_session_security_context(
                session,
                tenant_id=None,
                organization_id=None,
                user_id="public-client-invitation",
                platform_access=True,
            )
            results[name] = enterprise_client_invitation_service.accept_client_invitation(
                session,
                token=token,
                password="ConcurrentPassword123",
            )
            session.commit()
        except BaseException as exc:  # pragma: no cover - asserted in parent thread
            session.rollback()
            errors[name] = exc
        finally:
            session.close()
            if done is not None:
                done.set()

    first = threading.Thread(target=accept, kwargs={"name": "first"}, name="client-invite-first", daemon=True)
    second = threading.Thread(
        target=accept,
        kwargs={"name": "second", "done": second_done},
        name="client-invite-second",
        daemon=True,
    )
    first.start()
    try:
        assert first_holds_invitation.wait(timeout=5)
        second.start()
        assert not second_done.wait(timeout=0.25), "Second acceptance did not wait for the row lock"
    finally:
        release_first.set()
        first.join(timeout=5)
        if second.ident is not None:
            second.join(timeout=5)
        engine.dispose()

    assert not first.is_alive()
    assert not second.is_alive()
    assert set(results) == {"first"}
    assert set(errors) == {"second"}
    assert isinstance(errors["second"], enterprise_client_invitation_service.EnterpriseClientInvitationError)
    assert errors["second"].reason_code == "client_invitation_accepted"

    db_session.expire_all()
    client_user = db_session.query(User).filter(User.email == "concurrent.client@example.com").one()
    assert (
        db_session.query(func.count(OrganizationMembership.id))
        .filter(
            OrganizationMembership.organization_id == organization.id,
            OrganizationMembership.user_id == client_user.id,
        )
        .scalar()
        == 1
    )
    assert (
        db_session.query(func.count(PortfolioLocationAccessGrant.id))
        .filter(
            PortfolioLocationAccessGrant.organization_id == organization.id,
            PortfolioLocationAccessGrant.user_id == client_user.id,
            PortfolioLocationAccessGrant.location_group_id == group.id,
        )
        .scalar()
        == 1
    )
