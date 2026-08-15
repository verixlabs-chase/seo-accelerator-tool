from __future__ import annotations

import importlib.util
from collections import Counter
import threading
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
from sqlalchemy import create_engine, func, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import set_session_security_context
from app.models.business_location import BusinessLocation
from app.models.commercial_feature_activation import CommercialFeatureActivation
from app.models.cost_economics import CostLedgerEntry
from app.models.local_rank_grid import LocalRankGridPoint
from app.models.organization import Organization
from app.models.platform_job import PlatformJob
from app.models.portfolio import Portfolio
from app.models.user import User
from app.services import (
    business_location_service,
    durable_job_service,
    job_service,
    listing_discovery_service,
    local_rank_grid_service,
)
from app.services.commercial_plan_service import apply_commercial_plan
from app.services.cost_economics_service import (
    CostEconomicsError,
    authorize_reserved_provider_dispatch,
    reconcile_provider_cost,
    reserve_provider_cost,
)
from app.services.location_allowance_service import (
    ActiveLocationAllowanceError,
    ActiveLocationAllowanceExceeded,
    assert_provider_work_allowed,
    get_active_location_allowance,
)
from tests.test_listing_discovery import (
    _location_campaign as _listing_location_campaign,
    _provider_result as _listing_provider_result,
)
from tests.test_local_rank_grid import _location_campaign as _grid_location_campaign


pytestmark = pytest.mark.postgres_required

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "20260814_0155_commercial_active_location_allowance.py"
)


def _load_allowance_migration():
    spec = importlib.util.spec_from_file_location(
        "commercial_active_location_allowance_pg_0155",
        _MIGRATION_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_revision(connection, callback) -> None:
    context = MigrationContext.configure(connection)
    with Operations.context(context):
        callback()


def test_postgres_final_active_location_slot_has_one_winner(
    apply_migrations,
    db_session,
    monkeypatch,
) -> None:
    organization = db_session.query(Organization).order_by(Organization.id).first()
    assert organization is not None
    organization_id = organization.id
    apply_commercial_plan(
        db_session,
        organization_id=organization_id,
        plan_code="solo",
    )
    db_session.commit()
    assert (
        db_session.query(func.count(BusinessLocation.id))
        .filter(
            BusinessLocation.organization_id == organization_id,
            BusinessLocation.status == "active",
        )
        .scalar()
        == 0
    )
    # Close the read transaction before the worker sessions contend for the org row.
    db_session.commit()

    first_has_lock = threading.Event()
    release_first = threading.Event()
    second_attempting = threading.Event()
    second_done = threading.Event()
    original_assert_capacity = business_location_service.assert_active_location_capacity

    def blocking_assert_capacity(*args, **kwargs):
        if threading.current_thread().name == "active-location-second":
            second_attempting.set()
        allowance = original_assert_capacity(*args, **kwargs)
        if threading.current_thread().name == "active-location-first":
            first_has_lock.set()
            if not release_first.wait(timeout=5):
                raise AssertionError("Timed out while holding the final active-location slot")
        return allowance

    monkeypatch.setattr(
        business_location_service,
        "assert_active_location_capacity",
        blocking_assert_capacity,
    )

    engine = create_engine(str(apply_migrations["database_url"]), pool_pre_ping=True)
    session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    results: dict[str, dict[str, object]] = {}
    errors: dict[str, BaseException] = {}

    def worker(name: str, *, done: threading.Event | None = None) -> None:
        session = session_local()
        try:
            results[name] = business_location_service.create_business_location_with_portfolio(
                session,
                organization_id=organization_id,
                name=f"Concurrent location {name}",
                domain=f"concurrent-{name}.example",
                primary_city="Reno",
            )
            session.commit()
        except BaseException as exc:  # pragma: no cover - asserted in the parent thread
            session.rollback()
            errors[name] = exc
        finally:
            session.close()
            if done is not None:
                done.set()

    first_thread = threading.Thread(
        target=worker,
        kwargs={"name": "first"},
        name="active-location-first",
        daemon=True,
    )
    second_thread = threading.Thread(
        target=worker,
        kwargs={"name": "second", "done": second_done},
        name="active-location-second",
        daemon=True,
    )
    first_thread.start()
    try:
        assert first_has_lock.wait(timeout=5), "First writer never acquired the org row lock"
        second_thread.start()
        assert second_attempting.wait(timeout=5), "Second writer never attempted the final slot"
        assert not second_done.wait(timeout=0.25), (
            "Second writer finished without waiting for the organization row lock"
        )
    finally:
        release_first.set()
        first_thread.join(timeout=5)
        if second_thread.ident is not None:
            second_thread.join(timeout=5)
        engine.dispose()

    assert not first_thread.is_alive()
    assert not second_thread.is_alive()
    assert set(results) == {"first"}
    assert set(errors) == {"second"}
    assert isinstance(errors["second"], ActiveLocationAllowanceExceeded)
    assert errors["second"].reason_code == "active_location_allowance_exhausted"

    db_session.expire_all()
    active_location_ids = {
        row[0]
        for row in db_session.query(BusinessLocation.id)
        .filter(
            BusinessLocation.organization_id == organization_id,
            BusinessLocation.status == "active",
        )
        .all()
    }
    linked_portfolios = (
        db_session.query(Portfolio)
        .filter(
            Portfolio.organization_id == organization_id,
            Portfolio.business_location_id.in_(active_location_ids),
        )
        .all()
    )
    assert active_location_ids == {results["first"]["id"]}
    assert len(linked_portfolios) == 1


def test_app_role_can_lock_activation_truth_but_cannot_mutate_it(db_session) -> None:
    user = db_session.query(User).filter(User.email == "a@example.com").one()
    organization_id = str(user.tenant_id)
    db_session.commit()

    isolated = Session(bind=db_session.get_bind(), autocommit=False, autoflush=False)
    try:
        set_session_security_context(
            isolated,
            tenant_id=organization_id,
            organization_id=organization_id,
            user_id=user.id,
            platform_access=False,
        )
        organization = isolated.get(Organization, organization_id)
        assert organization is not None
        allowance = get_active_location_allowance(isolated, organization=organization)
        assert allowance.organization_id == organization_id

        with pytest.raises(DBAPIError):
            isolated.execute(
                text(
                    "UPDATE commercial_feature_activations "
                    "SET updated_at = :updated_at "
                    "WHERE code = 'active_location_allowance'"
                ),
                {"updated_at": datetime.now(UTC)},
            )
            isolated.flush()
    finally:
        isolated.rollback()
        isolated.close()

    state_attempt = Session(bind=db_session.get_bind(), autocommit=False, autoflush=False)
    try:
        set_session_security_context(
            state_attempt,
            tenant_id=organization_id,
            organization_id=organization_id,
            user_id=user.id,
            platform_access=False,
        )
        with pytest.raises(DBAPIError):
            state_attempt.execute(
                text(
                    "UPDATE commercial_feature_activations "
                    "SET state = 'observe' "
                    "WHERE code = 'active_location_allowance'"
                )
            )
            state_attempt.flush()
    finally:
        state_attempt.rollback()
        state_attempt.close()


def test_locked_allowance_refreshes_stale_plan_and_lifecycle_identity(
    apply_migrations,
    db_session,
) -> None:
    organization = db_session.query(Organization).order_by(Organization.id).first()
    assert organization is not None
    apply_commercial_plan(
        db_session,
        organization_id=organization.id,
        plan_code="multi_location",
    )
    db_session.commit()
    engine = create_engine(str(apply_migrations["database_url"]), pool_pre_ping=True)
    stale = Session(
        bind=engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
    updater = Session(bind=engine, autocommit=False, autoflush=False)
    try:
        stale_org = stale.get(Organization, organization.id)
        assert stale_org.plan_type == "multi_location"
        assert stale_org.status == "active"

        apply_commercial_plan(
            updater,
            organization_id=organization.id,
            plan_code="solo",
        )
        current = updater.get(Organization, organization.id)
        current.status = "suspended"
        updater.commit()

        allowance = get_active_location_allowance(stale, organization=stale_org)
        assert allowance.plan_code == "solo"
        assert allowance.included_locations == 1
        assert stale_org.status == "suspended"
        with pytest.raises(ActiveLocationAllowanceError) as exc_info:
            assert_provider_work_allowed(
                stale,
                organization_id=organization.id,
            )
        assert exc_info.value.reason_code == "organization_inactive_for_commercial_work"
    finally:
        stale.rollback()
        updater.rollback()
        stale.close()
        updater.close()
        engine.dispose()


def test_activation_flip_waits_for_inflight_app_role_allowance_decision(
    db_session,
) -> None:
    user = db_session.query(User).filter(User.email == "a@example.com").one()
    organization_id = str(user.tenant_id)
    activation = db_session.get(
        CommercialFeatureActivation,
        "active_location_allowance",
    )
    activation.state = "observe"
    db_session.commit()

    reader = Session(bind=db_session.get_bind(), autocommit=False, autoflush=False)
    set_session_security_context(
        reader,
        tenant_id=organization_id,
        organization_id=organization_id,
        user_id=user.id,
        platform_access=False,
    )
    organization = reader.get(Organization, organization_id)
    assert organization is not None
    allowance = get_active_location_allowance(reader, organization=organization)
    assert allowance.capacity_enforced is False

    update_started = threading.Event()
    update_done = threading.Event()
    errors: list[BaseException] = []

    def activate() -> None:
        owner = Session(bind=db_session.get_bind(), autocommit=False, autoflush=False)
        try:
            update_started.set()
            owner.execute(
                text(
                    "UPDATE commercial_feature_activations "
                    "SET state = 'enforced', updated_at = :updated_at "
                    "WHERE code = 'active_location_allowance'"
                ),
                {"updated_at": datetime.now(UTC)},
            )
            owner.commit()
        except BaseException as exc:  # pragma: no cover - asserted by parent thread
            owner.rollback()
            errors.append(exc)
        finally:
            owner.close()
            update_done.set()

    worker = threading.Thread(target=activate, daemon=True)
    worker.start()
    try:
        assert update_started.wait(timeout=5)
        assert not update_done.wait(timeout=0.25), (
            "Activation update overtook the in-flight FOR SHARE decision"
        )
    finally:
        reader.rollback()
        reader.close()
        worker.join(timeout=5)

    assert not worker.is_alive()
    assert errors == []
    assert update_done.is_set()
    db_session.expire_all()
    assert (
        db_session.get(CommercialFeatureActivation, "active_location_allowance").state
        == "enforced"
    )


def test_same_reservation_has_one_authorized_dispatch_winner(
    apply_migrations,
    db_session,
) -> None:
    organization = db_session.query(Organization).order_by(Organization.id).first()
    assert organization is not None
    reservation = reserve_provider_cost(
        db_session,
        organization_id=organization.id,
        provider_name="dataforseo",
        capability="rank_tracking",
        operation="google_organic_live_advanced",
        credential_owner="platform",
        quantity=1,
        idempotency_key="pg:one-dispatch-winner",
    )

    engine = create_engine(str(apply_migrations["database_url"]), pool_pre_ping=True)
    session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    start = threading.Barrier(2)
    provider_calls: list[str] = []
    outcomes: dict[str, str] = {}

    def dispatch(name: str) -> None:
        session = session_local()
        try:
            start.wait(timeout=5)
            authorized = authorize_reserved_provider_dispatch(
                session,
                reservation=reservation.id,
            )
            provider_calls.append(name)
            reconcile_provider_cost(
                session,
                reservation=authorized,
                provider_reported_cost=authorized.estimated_cost,
            )
            outcomes[name] = "dispatched"
        except CostEconomicsError as exc:
            session.rollback()
            outcomes[name] = exc.reason_code
        finally:
            session.close()

    threads = [
        threading.Thread(target=dispatch, args=(name,), daemon=True)
        for name in ("first", "second")
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=8)
    engine.dispose()

    assert all(not thread.is_alive() for thread in threads)
    assert len(provider_calls) == 1
    assert sorted(outcomes.values()) == [
        "dispatched",
        "provider_dispatch_already_finalized",
    ]
    db_session.expire_all()
    assert (
        db_session.query(CostLedgerEntry)
        .filter(
            CostLedgerEntry.reservation_id == reservation.id,
            CostLedgerEntry.event_type == "reconciliation",
        )
        .count()
        == 1
    )
    assert (
        db_session.query(CostLedgerEntry)
        .filter(
            CostLedgerEntry.reservation_id == reservation.id,
            CostLedgerEntry.event_type == "release",
        )
        .count()
        == 0
    )


def test_same_listing_run_has_one_provider_dispatch(
    apply_migrations,
    db_session,
    monkeypatch,
) -> None:
    user, campaign, _location = _listing_location_campaign(db_session)
    monkeypatch.setattr(listing_discovery_service, "_credential_owner", lambda *_args: "platform")
    monkeypatch.setattr(
        listing_discovery_service,
        "resolve_provider_credentials",
        lambda *_args: {"login": "api@example.com", "password": "secret"},
    )
    run, _created = listing_discovery_service.create_run(
        db_session,
        tenant_id=user.tenant_id,
        organization_id=campaign.organization_id,
        campaign_id=campaign.id,
        requested_by_user_id=user.id,
        idempotency_key="pg-one-listing-dispatch",
    )
    db_session.commit()

    provider_started = threading.Event()
    release_provider = threading.Event()
    second_done = threading.Event()
    calls: list[str] = []
    call_lock = threading.Lock()

    def search(_self, **_kwargs):
        with call_lock:
            calls.append("search")
        provider_started.set()
        if not release_provider.wait(timeout=8):
            raise AssertionError("Timed out while holding the listing provider call")
        return _listing_provider_result()

    monkeypatch.setattr(
        listing_discovery_service.DataForSeoBusinessListingsProvider,
        "search",
        search,
    )
    engine = create_engine(str(apply_migrations["database_url"]), pool_pre_ping=True)
    session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    outcomes: dict[str, dict[str, object]] = {}
    errors: list[BaseException] = []

    def worker(name: str, *, done: threading.Event | None = None) -> None:
        session = session_local()
        try:
            outcomes[name] = listing_discovery_service.dispatch_run(
                session,
                tenant_id=user.tenant_id,
                run_id=run.id,
            )
        except BaseException as exc:  # pragma: no cover - asserted by parent thread
            session.rollback()
            errors.append(exc)
        finally:
            session.close()
            if done is not None:
                done.set()

    first = threading.Thread(target=worker, args=("first",), daemon=True)
    second = threading.Thread(
        target=worker,
        args=("second",),
        kwargs={"done": second_done},
        daemon=True,
    )
    first.start()
    try:
        assert provider_started.wait(timeout=8)
        second.start()
        assert not second_done.wait(timeout=0.25), "Second worker bypassed the run fence"
    finally:
        release_provider.set()
        first.join(timeout=8)
        if second.ident is not None:
            second.join(timeout=8)
        engine.dispose()

    assert errors == []
    assert not first.is_alive()
    assert not second.is_alive()
    assert calls == ["search"]
    assert {row["status"] for row in outcomes.values()} == {"completed"}
    db_session.expire_all()
    assert (
        db_session.query(CostLedgerEntry)
        .filter(
            CostLedgerEntry.reservation_id == run.reservation_id,
            CostLedgerEntry.event_type == "reconciliation",
        )
        .count()
        == 1
    )


def test_same_grid_run_submits_each_point_once(
    apply_migrations,
    db_session,
    monkeypatch,
) -> None:
    organization = db_session.query(Organization).order_by(Organization.id).first()
    assert organization is not None
    campaign, _location, keywords = _grid_location_campaign(
        db_session,
        organization,
        name="PG Serialized Grid",
        city="Reno",
    )
    monkeypatch.setattr(local_rank_grid_service, "_credential_owner", lambda *_args: "platform")
    run, _created = local_rank_grid_service.create_run(
        db_session,
        tenant_id=organization.id,
        organization_id=organization.id,
        created_by_user_id=None,
        campaign_id=campaign.id,
        keyword_ids=[keywords[0].id],
        grid_size=3,
        radius_miles=2,
        idempotency_key="pg-one-grid-dispatch",
    )
    point_ids = {
        row[0]
        for row in db_session.query(LocalRankGridPoint.id)
        .filter(LocalRankGridPoint.run_id == run.id)
        .all()
    }
    db_session.commit()

    provider_started = threading.Event()
    release_provider = threading.Event()
    second_done = threading.Event()
    submitted_point_ids: list[str] = []
    call_lock = threading.Lock()

    class Provider:
        def submit(self, requests):
            with call_lock:
                submitted_point_ids.extend(item.point_id for item in requests)
            provider_started.set()
            if not release_provider.wait(timeout=8):
                raise AssertionError("Timed out while holding the grid provider call")
            return [
                {
                    "point_id": item.point_id,
                    "task_id": f"pg-{item.point_id}",
                    "status": "ranked",
                    "rank": 3,
                    "status_code": 20000,
                    "status_message": "complete",
                    "cost": Decimal("0.001"),
                }
                for item in requests
            ]

    provider = Provider()
    monkeypatch.setattr(local_rank_grid_service, "_provider_for_run", lambda *_args: provider)
    engine = create_engine(str(apply_migrations["database_url"]), pool_pre_ping=True)
    session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    outcomes: dict[str, dict[str, object]] = {}
    errors: list[BaseException] = []

    def worker(name: str, *, done: threading.Event | None = None) -> None:
        session = session_local()
        try:
            outcomes[name] = local_rank_grid_service.dispatch_run(
                session,
                run_id=run.id,
                tenant_id=organization.id,
            )
        except BaseException as exc:  # pragma: no cover - asserted by parent thread
            session.rollback()
            errors.append(exc)
        finally:
            session.close()
            if done is not None:
                done.set()

    first = threading.Thread(target=worker, args=("first",), daemon=True)
    second = threading.Thread(
        target=worker,
        args=("second",),
        kwargs={"done": second_done},
        daemon=True,
    )
    first.start()
    try:
        assert provider_started.wait(timeout=8)
        second.start()
        assert not second_done.wait(timeout=0.25), "Second worker bypassed the grid fence"
    finally:
        release_provider.set()
        first.join(timeout=8)
        if second.ident is not None:
            second.join(timeout=8)
        engine.dispose()

    assert errors == []
    assert not first.is_alive()
    assert not second.is_alive()
    assert Counter(submitted_point_ids) == Counter({point_id: 1 for point_id in point_ids})
    assert {row["status"] for row in outcomes.values()} == {"completed"}


def test_expired_listing_claim_closes_ambiguously_without_second_provider_call(
    apply_migrations,
    db_session,
    monkeypatch,
) -> None:
    user, campaign, _location = _listing_location_campaign(db_session)
    monkeypatch.setattr(listing_discovery_service, "_credential_owner", lambda *_args: "platform")
    calls: list[str] = []
    monkeypatch.setattr(
        listing_discovery_service.DataForSeoBusinessListingsProvider,
        "search",
        lambda _self, **_kwargs: calls.append("search") or _listing_provider_result(),
    )
    run, _created = listing_discovery_service.create_run(
        db_session,
        tenant_id=user.tenant_id,
        organization_id=campaign.organization_id,
        campaign_id=campaign.id,
        requested_by_user_id=user.id,
        idempotency_key="pg-expired-listing-dispatch",
    )
    job = (
        db_session.query(PlatformJob)
        .filter(
            PlatformJob.job_type == listing_discovery_service.JOB_TYPE,
            PlatformJob.entity_id == run.id,
        )
        .one()
    )
    now = datetime.now(UTC)
    run.status = "running"
    run.started_at = now - timedelta(minutes=5)
    job.status = job_service.JOB_STATUS_RUNNING
    job.locked_by = "dead-worker"
    job.locked_at = now - timedelta(minutes=5)
    job.lease_expires_at = now - timedelta(minutes=4)
    db_session.commit()

    engine = create_engine(str(apply_migrations["database_url"]), pool_pre_ping=True)
    worker = Session(bind=engine, autocommit=False, autoflush=False)
    try:
        claimed = job_service.claim_jobs(
            worker,
            worker_id="replacement-worker",
            limit=25,
            lease_seconds=120,
            now=now,
        )
        assert job.id in {row.id for row in claimed}
        worker.commit()
        outcome = durable_job_service.execute_claimed_job(worker, job_id=job.id)
        assert outcome == {"job_id": job.id, "status": job_service.JOB_STATUS_COMPLETED}
    finally:
        worker.close()
        engine.dispose()

    assert calls == []
    db_session.expire_all()
    assert db_session.get(PlatformJob, job.id).status == job_service.JOB_STATUS_COMPLETED
    assert db_session.get(type(run), run.id).status == "failed"
    assert (
        db_session.query(CostLedgerEntry)
        .filter(
            CostLedgerEntry.reservation_id == run.reservation_id,
            CostLedgerEntry.event_type == "reconciliation",
        )
        .count()
        == 1
    )


def test_expired_grid_claim_preserves_pending_and_never_resubmits_queued_points(
    apply_migrations,
    db_session,
    monkeypatch,
) -> None:
    organization = db_session.query(Organization).order_by(Organization.id).first()
    assert organization is not None
    campaign, _location, keywords = _grid_location_campaign(
        db_session,
        organization,
        name="PG Expired Grid",
        city="Reno",
    )
    monkeypatch.setattr(local_rank_grid_service, "_credential_owner", lambda *_args: "platform")
    provider_calls: list[str] = []

    class Provider:
        def submit(self, _requests):
            provider_calls.append("submit")
            return []

    monkeypatch.setattr(
        local_rank_grid_service,
        "_provider_for_run",
        lambda *_args: Provider(),
    )
    run, _created = local_rank_grid_service.create_run(
        db_session,
        tenant_id=organization.id,
        organization_id=organization.id,
        created_by_user_id=None,
        campaign_id=campaign.id,
        keyword_ids=[keywords[0].id],
        grid_size=3,
        radius_miles=2,
        idempotency_key="pg-expired-grid-dispatch",
    )
    pending = (
        db_session.query(LocalRankGridPoint)
        .filter(LocalRankGridPoint.run_id == run.id)
        .order_by(LocalRankGridPoint.grid_index)
        .first()
    )
    pending.status = "pending"
    pending.provider_task_id = f"already-submitted-{pending.id}"
    run.status = "submitting"
    job = (
        db_session.query(PlatformJob)
        .filter(
            PlatformJob.job_type == local_rank_grid_service.JOB_TYPE,
            PlatformJob.entity_id == run.id,
        )
        .one()
    )
    now = datetime.now(UTC)
    job.status = job_service.JOB_STATUS_RUNNING
    job.locked_by = "dead-grid-worker"
    job.locked_at = now - timedelta(minutes=5)
    job.lease_expires_at = now - timedelta(minutes=4)
    db_session.commit()

    engine = create_engine(str(apply_migrations["database_url"]), pool_pre_ping=True)
    replacement = Session(bind=engine, autocommit=False, autoflush=False)
    try:
        claimed = job_service.claim_jobs(
            replacement,
            worker_id="replacement-grid-worker",
            limit=25,
            lease_seconds=120,
            now=now,
        )
        assert job.id in {row.id for row in claimed}
        replacement.commit()
        outcome = durable_job_service.execute_claimed_job(replacement, job_id=job.id)
        assert outcome == {"job_id": job.id, "status": job_service.JOB_STATUS_COMPLETED}
    finally:
        replacement.close()
        engine.dispose()

    assert provider_calls == []
    db_session.expire_all()
    assert db_session.get(PlatformJob, job.id).status == job_service.JOB_STATUS_COMPLETED
    current_run = db_session.get(type(run), run.id)
    assert current_run.status == "partial"
    points = (
        db_session.query(LocalRankGridPoint)
        .filter(LocalRankGridPoint.run_id == run.id)
        .all()
    )
    assert [point.status for point in points].count("pending") == 1
    assert [point.status for point in points].count("failed") == 8
    assert (
        db_session.query(CostLedgerEntry)
        .filter(
            CostLedgerEntry.reservation_id == run.reservation_id,
            CostLedgerEntry.event_type == "reconciliation",
        )
        .count()
        == 1
    )


def test_migration_org_fence_serializes_lazy_plan_reconciliation(
    apply_migrations,
    db_session,
    monkeypatch,
) -> None:
    migration = _load_allowance_migration()
    organization = db_session.query(Organization).order_by(Organization.id).first()
    assert organization is not None
    organization_id = organization.id
    db_session.commit()
    engine = create_engine(str(apply_migrations["database_url"]), pool_pre_ping=True)

    # Recreate the 0154/0155 boundary while retaining the additive catalog
    # rows, exactly as the expand-only downgrade promises.
    with engine.begin() as connection:
        _run_revision(connection, migration.downgrade)
        connection.execute(
            text(
                "DELETE FROM entitlements "
                "WHERE organization_id = :organization_id "
                "AND code = 'limit.active_locations'"
            ),
            {"organization_id": organization_id},
        )

    migration_holds_org_lock = threading.Event()
    release_migration = threading.Event()
    plan_change_started = threading.Event()
    plan_change_done = threading.Event()
    errors: list[BaseException] = []
    original_template = migration._template
    first_template_call = True

    def paused_template(plan_code):
        nonlocal first_template_call
        if first_template_call:
            first_template_call = False
            migration_holds_org_lock.set()
            if not release_migration.wait(timeout=8):
                raise AssertionError("Timed out while holding the migration organization fence")
        return original_template(plan_code)

    monkeypatch.setattr(migration, "_template", paused_template)

    def run_migration() -> None:
        try:
            with engine.begin() as connection:
                _run_revision(connection, migration.upgrade)
        except BaseException as exc:  # pragma: no cover - asserted by parent thread
            errors.append(exc)

    def change_plan() -> None:
        session = Session(bind=engine, autocommit=False, autoflush=False)
        try:
            plan_change_started.set()
            apply_commercial_plan(
                session,
                organization_id=organization_id,
                plan_code="multi_location",
            )
            session.commit()
        except BaseException as exc:  # pragma: no cover - asserted by parent thread
            session.rollback()
            errors.append(exc)
        finally:
            session.close()
            plan_change_done.set()

    migration_thread = threading.Thread(target=run_migration, daemon=True)
    plan_thread = threading.Thread(target=change_plan, daemon=True)
    migration_thread.start()
    try:
        assert migration_holds_org_lock.wait(timeout=8)
        plan_thread.start()
        assert plan_change_started.wait(timeout=5)
        assert not plan_change_done.wait(timeout=0.25), (
            "Plan reconciliation overtook the migration organization fence"
        )
    finally:
        release_migration.set()
        migration_thread.join(timeout=10)
        if plan_thread.ident is not None:
            plan_thread.join(timeout=10)

    assert not migration_thread.is_alive()
    assert not plan_thread.is_alive()
    assert errors == []
    with engine.connect() as connection:
        final = connection.execute(
            text(
                "SELECT o.plan_type, o.tier_version, e.limit_value "
                "FROM organizations o "
                "JOIN entitlements e ON e.organization_id = o.id "
                "AND e.code = 'limit.active_locations' "
                "WHERE o.id = :organization_id"
            ),
            {"organization_id": organization_id},
        ).mappings().one()
        activation_state = connection.execute(
            text(
                "SELECT state FROM commercial_feature_activations "
                "WHERE code = 'active_location_allowance'"
            )
        ).scalar_one()
    engine.dispose()
    assert final == {
        "plan_type": "multi_location",
        "tier_version": 1,
        "limit_value": 10,
    }
    assert activation_state == "observe"
