import os
os.environ["APP_ENV"] = "test"
if os.getenv("DATABASE_URL"):
    os.environ["POSTGRES_DSN"] = os.environ["DATABASE_URL"]

# THEN import anything else
import shutil
import tempfile
import time
import uuid
import socket
import threading
from datetime import UTC, datetime
from typing import Callable, Generator
from pathlib import Path
import pytest
import httpx
import uvicorn
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

import app.db.session as db_session_module
import app.tasks.tasks as tasks_module
from app.core.passwords import hash_password
from app.services.operational_telemetry_service import reset_operational_telemetry

from app.models.authority import Backlink, BacklinkOpportunity, Citation, OutreachCampaign, OutreachContact  # noqa: F401
from app.models.competitor import Competitor, CompetitorPage, CompetitorRanking, CompetitorSignal  # noqa: F401
from app.models.content import ContentAsset, ContentQcEvent, EditorialCalendar, InternalLinkMap  # noqa: F401
from app.models.crawl import CrawlRun, Page, TechnicalIssue  # noqa: F401
from app.models.entity import CompetitorEntity, EntityAnalysisRun, PageEntity  # noqa: F401
from app.models.experiment import Experiment, ExperimentAssignment, ExperimentOutcome  # noqa: F401
from app.models.causal_mechanism import FeatureImpactEdge, PolicyFeatureEdge  # noqa: F401
from app.models.intelligence import AnomalyEvent, CampaignMilestone, IntelligenceScore, StrategyRecommendation  # noqa: F401
from app.models.local import LocalHealthSnapshot, LocalProfile, Review, ReviewVelocitySnapshot  # noqa: F401
from app.models.learning_metric_snapshot import LearningMetricSnapshot  # noqa: F401
from app.models.learning_report import LearningReport  # noqa: F401
from app.models.knowledge_graph import KnowledgeEdge, KnowledgeNode  # noqa: F401
from app.models.organization import Organization  # noqa: F401
from app.models.industry_intelligence import IndustryIntelligenceModel  # noqa: F401
from app.models.intelligence_model_registry import IntelligenceModelRegistryState  # noqa: F401
from app.models.organization_membership import OrganizationMembership  # noqa: F401
from app.models.organization_provider_credential import OrganizationProviderCredential  # noqa: F401
from app.models.platform_provider_credential import PlatformProviderCredential  # noqa: F401
from app.models.policy_performance import PolicyPerformance  # noqa: F401
from app.models.provider_health import ProviderHealthState  # noqa: F401
from app.models.provider_metric import ProviderExecutionMetric  # noqa: F401
from app.models.provider_policy import ProviderPolicy  # noqa: F401
from app.models.provider_quota import ProviderQuotaState  # noqa: F401
from app.models.rank import CampaignKeyword, KeywordCluster, Ranking, RankingSnapshot  # noqa: F401
from app.models.reference_library import (
    ReferenceLibraryActivation,  # noqa: F401
    ReferenceLibraryArtifact,  # noqa: F401
    ReferenceLibraryValidationRun,  # noqa: F401
    ReferenceLibraryVersion,  # noqa: F401
)
from app.models.reporting import MonthlyReport, ReportArtifact, ReportDeliveryEvent, ReportSchedule, ReportTemplateVersion  # noqa: F401
from app.models.role import Role, UserRole
from app.models.strategy_evolution_log import StrategyEvolutionLog  # noqa: F401
from app.models.sub_account import SubAccount  # noqa: F401
from app.models.tenant import Tenant
from app.models.temporal import MomentumMetric, StrategyPhaseHistory, TemporalSignalSnapshot  # noqa: F401
from app.models.user import User
from app.intelligence.knowledge_graph.update_engine import reset_graph_write_batcher
from tests.fixtures.intelligence_graph_factory import create_intelligence_graph
from tests.helpers.economic_setup import ensure_test_tier_profile, provision_test_organization



def _run_alembic_upgrade(backend_dir: Path, database_url: str) -> None:
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    cfg.set_main_option("prepend_sys_path", str(backend_dir))
    cfg.set_main_option("sqlalchemy.url", database_url)
    os.environ["DATABASE_URL"] = database_url
    os.environ["POSTGRES_DSN"] = database_url
    command.upgrade(cfg, "head")


def pytest_configure(config: pytest.Config) -> None:
    workers = getattr(config.option, "numprocesses", None)
    if workers and int(workers) > 1:
        pytest.exit("Test DB path does not support pytest-xdist parallel workers.")


def _is_sqlite_url(database_url: str) -> bool:
    return database_url.startswith("sqlite")


def _resolve_test_database_url() -> str | None:
    for env_name in ("DATABASE_URL", "POSTGRES_DSN"):
        value = os.getenv(env_name, "").strip()
        if value:
            return value
    return None


def _uses_postgres_test_backend() -> bool:
    database_url = _resolve_test_database_url()
    return bool(database_url) and not _is_sqlite_url(database_url)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    del config
    postgres_backend_enabled = _uses_postgres_test_backend()

    for item in items:
        path = str(item.fspath)
        normalized = path.replace("\\", "/")

        if "/tests/load/" in normalized:
            item.add_marker(pytest.mark.load)
            item.add_marker(pytest.mark.postgres_required)
        elif "/tests/integration/" in normalized:
            item.add_marker(pytest.mark.integration)
        elif "/tests/" in normalized:
            item.add_marker(pytest.mark.unit)

        if item.get_closest_marker("postgres_required") and not postgres_backend_enabled:
            item.add_marker(
                pytest.mark.skip(
                    reason=(
                        "requires PostgreSQL test backend; set DATABASE_URL or POSTGRES_DSN "
                        "to a PostgreSQL test database to run this test"
                    )
                )
            )


def _create_test_engine(database_url: str):
    if _is_sqlite_url(database_url):
        return create_engine(
            database_url,
            connect_args={"check_same_thread": False, "timeout": 30},
            poolclass=NullPool,
        )
    return create_engine(database_url, poolclass=NullPool)


def _verify_required_tables(database_url: str) -> None:
    verification_engine = _create_test_engine(database_url)
    try:
        inspector = inspect(verification_engine)
        required_tables = [
            "crawl_runs",
            "strategy_cohort_patterns",
            "recommendation_executions",
            "recommendation_outcomes",
            "intelligence_metrics_snapshots",
            "intelligence_model_registry_states",
            "industry_intelligence_models",
            "experiment_outcomes",
            "experiment_assignments",
            "experiments",
            "policy_performance",
            "causal_feature_edges",
            "policy_feature_edges",
            "learning_metrics",
            "learning_reports",
            "knowledge_nodes",
            "knowledge_edges",
        ]
        missing = [table_name for table_name in required_tables if not inspector.has_table(table_name)]
    finally:
        verification_engine.dispose()
    if missing:
        raise RuntimeError(
            "Alembic migration parity check failed; missing tables: "
            + ", ".join(missing)
            + " (db="
            + database_url
            + ")"
        )


def _reset_external_test_schema(database_url: str) -> None:
    engine = _create_test_engine(database_url)
    try:
        with engine.begin() as conn:
            conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
    finally:
        engine.dispose()




def _seed_intelligence_state(session: Session) -> None:
    if session.query(IntelligenceModelRegistryState).filter(
        IntelligenceModelRegistryState.registry_name == "autonomous_model_registry"
    ).one_or_none() is None:
        session.add(
            IntelligenceModelRegistryState(
                registry_name="autonomous_model_registry",
                payload={"models": {}},
                updated_at=datetime.now(UTC),
            )
        )

    if session.query(IndustryIntelligenceModel).filter(
        IndustryIntelligenceModel.industry_id == "unknown"
    ).one_or_none() is None:
        session.add(
            IndustryIntelligenceModel(
                industry_id="unknown",
                industry_name="unknown",
                pattern_distribution={},
                strategy_success_rates={},
                avg_rank_delta=0.0,
                avg_traffic_delta=0.0,
                confidence_score=0.0,
                sample_size=0,
                support_state={},
                last_updated=datetime.now(UTC),
            )
        )

def _reset_external_test_database(engine) -> None:
    if engine.dialect.name == "sqlite":
        return
    inspector = inspect(engine)
    tables = [table_name for table_name in inspector.get_table_names() if table_name != "alembic_version"]
    if not tables:
        return
    joined_tables = ", ".join(f'"{table_name}"' for table_name in tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE TABLE {joined_tables} RESTART IDENTITY CASCADE"))
@pytest.fixture(scope="session", autouse=True)
def apply_migrations() -> Generator[dict[str, object], None, None]:
    print("apply_migrations: start", flush=True)
    backend_dir = Path(__file__).resolve().parents[1]
    explicit_database_url = _resolve_test_database_url()
    if explicit_database_url and not _is_sqlite_url(explicit_database_url):
        database_url = explicit_database_url
        os.environ["DATABASE_URL"] = database_url
        os.environ["POSTGRES_DSN"] = database_url

        from app.core.settings import get_settings

        get_settings.cache_clear()
        print(f"[tests] DATABASE_URL={database_url}")
        db_session_module.reset_engine_state()
        print("apply_migrations: reset external schema", flush=True)
        _reset_external_test_schema(database_url)
        print("apply_migrations: run alembic upgrade head", flush=True)
        _run_alembic_upgrade(backend_dir, database_url)
        print("apply_migrations: before verify_required_tables", flush=True)
        _verify_required_tables(database_url)
        print("apply_migrations: yielding", flush=True)
        yield {"database_url": database_url, "mode": "external"}
        return

    temp_dir = Path(tempfile.mkdtemp(prefix="pytest-db-"))
    template_db_path = temp_dir / f"template-{uuid.uuid4().hex}.sqlite3"
    database_url = f"sqlite:///{template_db_path.as_posix()}"
    os.environ["DATABASE_URL"] = database_url
    os.environ["POSTGRES_DSN"] = database_url

    from app.core.settings import get_settings

    get_settings.cache_clear()
    print(f"[tests] DATABASE_URL={database_url}")
    db_session_module.reset_engine_state()
    _run_alembic_upgrade(backend_dir, database_url)
    print("apply_migrations: before verify_required_tables", flush=True)
    _verify_required_tables(database_url)
    print("apply_migrations: yielding", flush=True)
    yield {
        "database_url": database_url,
        "mode": "sqlite",
        "template_db_path": template_db_path,
        "temp_dir": temp_dir,
    }
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture(scope="session", autouse=True)
def bind_module_session_factories(apply_migrations: dict[str, object]) -> Generator[None, None, None]:
    print("bind_module_session_factories: start", flush=True)
    database_url = str(apply_migrations["database_url"])
    bootstrap_engine = _create_test_engine(database_url)
    bootstrap_session_local = sessionmaker(bind=bootstrap_engine, autocommit=False, autoflush=False)

    db_session_module.bind_session_factory_for_tests(bootstrap_session_local)

    import app.api.v1.crawl as crawl_api_module

    tasks_module.SessionLocal = db_session_module.SessionLocal
    crawl_api_module.SessionLocal = db_session_module.SessionLocal

    # Import app after rebinding to avoid stale SessionLocal capture in route modules.
    print("bind_module_session_factories: before import app.main", flush=True)
    import app.main  # noqa: F401
    print("bind_module_session_factories: after import app.main", flush=True)

    yield
    bootstrap_engine.dispose()


@pytest.fixture()
def db_session(apply_migrations: dict[str, object]) -> Generator[Session, None, None]:
    mode = str(apply_migrations["mode"])
    test_db_path: Path | None = None
    if mode == "sqlite":
        template_db_path = Path(str(apply_migrations["template_db_path"]))
        test_db_path = template_db_path.parent / f"{uuid.uuid4().hex}.sqlite3"
        shutil.copy2(template_db_path, test_db_path)
        database_url = f"sqlite:///{test_db_path.as_posix()}"
    else:
        database_url = str(apply_migrations["database_url"])
    engine = _create_test_engine(database_url)
    if mode != "sqlite":
        _reset_external_test_database(engine)
    test_session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    test_session = test_session_local()
    reset_graph_write_batcher()

    # Ensure eager Celery tasks read/write against the same committed test DB.
    db_session_module.bind_session_factory_for_tests(test_session_local)
    tasks_module.SessionLocal = db_session_module.SessionLocal
    import app.api.v1.crawl as crawl_api_module

    crawl_api_module.SessionLocal = db_session_module.SessionLocal

    tenant_a = Tenant(id=str(uuid.uuid4()), name="Tenant A", created_at=datetime.now(UTC))
    tenant_b = Tenant(id=str(uuid.uuid4()), name="Tenant B", created_at=datetime.now(UTC))
    test_tier_profile = ensure_test_tier_profile(test_session)
    org_a = Organization(
        id=tenant_a.id,
        name=f"Org-{tenant_a.id[:8]}",
        plan_type="standard",
        billing_mode="subscription",
        status="active",
        tier_profile_id=test_tier_profile.id,
        tier_version=test_tier_profile.version,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    org_b = Organization(
        id=tenant_b.id,
        name=f"Org-{tenant_b.id[:8]}",
        plan_type="standard",
        billing_mode="subscription",
        status="active",
        tier_profile_id=test_tier_profile.id,
        tier_version=test_tier_profile.version,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    role_tenant_admin = Role(id="tenant_admin", name="tenant_admin", created_at=datetime.now(UTC))
    role_platform_admin = Role(id="platform_admin", name="platform_admin", created_at=datetime.now(UTC))
    role_platform_owner = Role(id="platform_owner", name="platform_owner", created_at=datetime.now(UTC))
    role_org_admin = Role(id="org_admin", name="org_admin", created_at=datetime.now(UTC))
    role_org_owner = Role(id="org_owner", name="org_owner", created_at=datetime.now(UTC))
    user_a = User(
        id=str(uuid.uuid4()),
        tenant_id=tenant_a.id,
        email="a@example.com",
        hashed_password=hash_password("pass-a"),
        created_at=datetime.now(UTC),
        is_active=True,
        is_platform_user=False,
        platform_role=None,
    )
    user_b = User(
        id=str(uuid.uuid4()),
        tenant_id=tenant_b.id,
        email="b@example.com",
        hashed_password=hash_password("pass-b"),
        created_at=datetime.now(UTC),
        is_active=True,
        is_platform_user=False,
        platform_role=None,
    )
    platform_admin_user = User(
        id=str(uuid.uuid4()),
        tenant_id=tenant_a.id,
        email="platform-admin@example.com",
        hashed_password=hash_password("pass-platform-admin"),
        created_at=datetime.now(UTC),
        is_active=True,
        is_platform_user=True,
        platform_role="platform_admin",
    )
    platform_owner_user = User(
        id=str(uuid.uuid4()),
        tenant_id=tenant_a.id,
        email="platform-owner@example.com",
        hashed_password=hash_password("pass-platform-owner"),
        created_at=datetime.now(UTC),
        is_active=True,
        is_platform_user=True,
        platform_role="platform_owner",
    )
    org_admin_user = User(
        id=str(uuid.uuid4()),
        tenant_id=tenant_a.id,
        email="org-admin@example.com",
        hashed_password=hash_password("pass-org-admin"),
        created_at=datetime.now(UTC),
        is_active=True,
        is_platform_user=False,
        platform_role=None,
    )
    org_owner_user = User(
        id=str(uuid.uuid4()),
        tenant_id=tenant_a.id,
        email="org-owner@example.com",
        hashed_password=hash_password("pass-org-owner"),
        created_at=datetime.now(UTC),
        is_active=True,
        is_platform_user=False,
        platform_role=None,
    )
    test_session.add_all(
        [
            tenant_a,
            tenant_b,
            org_a,
            org_b,
            role_tenant_admin,
            role_platform_admin,
            role_platform_owner,
            role_org_admin,
            role_org_owner,
            user_a,
            user_b,
            platform_admin_user,
            platform_owner_user,
            org_admin_user,
            org_owner_user,
        ]
    )
    # Persist principals first so Postgres sees referenced rows before FK-dependent inserts.
    test_session.commit()
    test_session.add_all(
        [
            UserRole(id=str(uuid.uuid4()), user_id=user_a.id, role_id=role_tenant_admin.id, created_at=datetime.now(UTC)),
            UserRole(id=str(uuid.uuid4()), user_id=user_b.id, role_id=role_tenant_admin.id, created_at=datetime.now(UTC)),
            UserRole(
                id=str(uuid.uuid4()),
                user_id=platform_admin_user.id,
                role_id=role_platform_admin.id,
                created_at=datetime.now(UTC),
            ),
            UserRole(
                id=str(uuid.uuid4()),
                user_id=platform_owner_user.id,
                role_id=role_platform_owner.id,
                created_at=datetime.now(UTC),
            ),
            UserRole(
                id=str(uuid.uuid4()),
                user_id=org_admin_user.id,
                role_id=role_org_admin.id,
                created_at=datetime.now(UTC),
            ),
            UserRole(
                id=str(uuid.uuid4()),
                user_id=org_owner_user.id,
                role_id=role_org_owner.id,
                created_at=datetime.now(UTC),
            ),
        ]
    )
    # Ensure users exist before memberships reference them.
    test_session.flush()
    test_session.add_all(
        [
            OrganizationMembership(
                id=str(uuid.uuid4()),
                user_id=user_a.id,
                organization_id=org_a.id,
                role="org_admin",
                status="active",
                created_at=datetime.now(UTC),
            ),
            OrganizationMembership(
                id=str(uuid.uuid4()),
                user_id=user_b.id,
                organization_id=org_b.id,
                role="org_admin",
                status="active",
                created_at=datetime.now(UTC),
            ),
            OrganizationMembership(
                id=str(uuid.uuid4()),
                user_id=platform_admin_user.id,
                organization_id=org_a.id,
                role="org_admin",
                status="active",
                created_at=datetime.now(UTC),
            ),
            OrganizationMembership(
                id=str(uuid.uuid4()),
                user_id=platform_owner_user.id,
                organization_id=org_a.id,
                role="org_owner",
                status="active",
                created_at=datetime.now(UTC),
            ),
            OrganizationMembership(
                id=str(uuid.uuid4()),
                user_id=org_admin_user.id,
                organization_id=org_a.id,
                role="org_admin",
                status="active",
                created_at=datetime.now(UTC),
            ),
            OrganizationMembership(
                id=str(uuid.uuid4()),
                user_id=org_owner_user.id,
                organization_id=org_a.id,
                role="org_owner",
                status="active",
                created_at=datetime.now(UTC),
            ),
        ]
    )
    test_session.commit()
    provision_test_organization(test_session, org_a)
    provision_test_organization(test_session, org_b)
    _seed_intelligence_state(test_session)
    test_session.commit()
    yield test_session
    test_session.close()
    engine.dispose()
    db_session_module.reset_engine_state()
    if test_db_path is not None:
        for _ in range(5):
            try:
                test_db_path.unlink(missing_ok=True)
                break
            except PermissionError:
                time.sleep(0.05)


@pytest.fixture(autouse=True)
def reset_knowledge_graph_batcher_fixture() -> Generator[None, None, None]:
    reset_graph_write_batcher()
    yield
    reset_graph_write_batcher()




@pytest.fixture()
def intelligence_graph(db_session: Session) -> dict[str, object]:
    return create_intelligence_graph(db_session)

@pytest.fixture()
def client(db_session: Session) -> Generator[object, None, None]:
    from app.main import app
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind(("127.0.0.1", 0))
    host, port = server_socket.getsockname()
    server_socket.close()

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",
        lifespan="off",
    )
    server = uvicorn.Server(config)
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    base_url = f"http://{host}:{port}"
    raw_test_client = httpx.Client(base_url=base_url, timeout=10.0)

    deadline = time.time() + 10
    last_error: Exception | None = None
    while time.time() < deadline:
        if server.started:
            break
        try:
            raw_test_client.get("/openapi.json")
            break
        except Exception as exc:
            last_error = exc
            time.sleep(0.05)
    else:
        raw_test_client.close()
        server.should_exit = True
        server_thread.join(timeout=5)
        raise RuntimeError(f"Test server did not start: {last_error!r}")

    class _Client:
        def request(self, method: str, url: str, **kwargs):
            db_session.commit()
            db_session.expire_all()
            response = raw_test_client.request(method, url, **kwargs)
            db_session.expire_all()
            return response

        def get(self, url: str, **kwargs):
            return self.request("GET", url, **kwargs)

        def post(self, url: str, **kwargs):
            return self.request("POST", url, **kwargs)

        def put(self, url: str, **kwargs):
            return self.request("PUT", url, **kwargs)

        def patch(self, url: str, **kwargs):
            return self.request("PATCH", url, **kwargs)

        def delete(self, url: str, **kwargs):
            return self.request("DELETE", url, **kwargs)

        def close(self) -> None:
            raw_test_client.close()

    test_client = _Client()
    try:
        yield test_client
    finally:
        db_session.rollback()
        db_session.expire_all()
        test_client.close()
        server.should_exit = True
        server_thread.join(timeout=5)





def create_test_tenant(session: Session, tenant_id: str | None = None, name: str = "Test Tenant") -> Tenant:
    resolved_tenant_id = tenant_id or str(uuid.uuid4())
    tenant = session.query(Tenant).filter(Tenant.id == resolved_tenant_id).one_or_none()
    if tenant is not None:
        return tenant
    tenant = Tenant(
        id=resolved_tenant_id,
        name=name if tenant_id is None else f"{name} {resolved_tenant_id[:8]}",
        status="Active",
        created_at=datetime.now(UTC),
    )
    session.add(tenant)
    session.flush()
    return tenant


@pytest.fixture(name="create_test_tenant")
def create_test_tenant_fixture(db_session: Session) -> Callable[..., Tenant]:
    def _create_test_tenant(*, tenant_id: str | None = None, name: str | None = None) -> Tenant:
        return create_test_tenant(
            session=db_session,
            tenant_id=tenant_id,
            name=name or "Test Tenant",
        )

    return _create_test_tenant

@pytest.fixture()
def create_test_org(
    db_session: Session,
    create_test_tenant: Callable[..., Tenant],
) -> Callable[..., Organization]:
    def _create_test_org(
        *,
        organization_id: str | None = None,
        tenant_id: str | None = None,
        name: str | None = None,
        status: str = "active",
    ) -> Organization:
        resolved_tenant_id = tenant_id or organization_id
        tenant = create_test_tenant(tenant_id=resolved_tenant_id)
        resolved_org_id = organization_id or tenant.id
        organization = db_session.query(Organization).filter(Organization.id == resolved_org_id).one_or_none()
        if organization is None:
            test_tier_profile = ensure_test_tier_profile(db_session)
            organization = Organization(
                id=resolved_org_id,
                name=name or f"Org-{resolved_org_id[:8]}",
                plan_type="standard",
                billing_mode="subscription",
                status=status,
                tier_profile_id=test_tier_profile.id,
                tier_version=test_tier_profile.version,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            db_session.add(organization)
            db_session.flush()
        return organization

    return _create_test_org


@pytest.fixture()
def create_test_sub_account(
    db_session: Session,
    create_test_org: Callable[..., Organization],
) -> Callable[..., SubAccount]:
    def _create_test_sub_account(
        *,
        sub_account_id: str | None = None,
        organization_id: str | None = None,
        tenant_id: str | None = None,
        name: str = "Test SubAccount",
        status: str = "active",
    ) -> SubAccount:
        organization = create_test_org(organization_id=organization_id, tenant_id=tenant_id)
        resolved_sub_account_id = sub_account_id or str(uuid.uuid4())
        sub_account = db_session.query(SubAccount).filter(SubAccount.id == resolved_sub_account_id).one_or_none()
        if sub_account is None:
            sub_account = SubAccount(
                id=resolved_sub_account_id,
                organization_id=organization.id,
                name=name,
                status=status,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            db_session.add(sub_account)
            db_session.flush()
        return sub_account

    return _create_test_sub_account


@pytest.fixture(autouse=True)
def reset_operational_metrics_fixture() -> Generator[None, None, None]:
    reset_operational_telemetry()
    yield
    reset_operational_telemetry()


def create_test_campaign(
    session: Session,
    org_id: str,
    *,
    tenant_id: str | None = None,
    name: str | None = None,
    domain: str | None = None,
):
    from app.models.campaign import Campaign

    resolved_tenant_id = tenant_id or org_id
    tenant = session.query(Tenant).filter(Tenant.id == resolved_tenant_id).one_or_none()
    if tenant is None:
        tenant = create_test_tenant(session, tenant_id=resolved_tenant_id, name="Campaign Tenant")

    organization = session.query(Organization).filter(Organization.id == org_id).one_or_none()
    if organization is None:
        test_tier_profile = ensure_test_tier_profile(session)
        organization = Organization(
            id=org_id,
            name=f"Org-{org_id[:8]}",
            plan_type="standard",
            billing_mode="subscription",
            status="active",
            tier_profile_id=test_tier_profile.id,
            tier_version=test_tier_profile.version,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        session.add(organization)
        session.flush()

    campaign = Campaign(
        tenant_id=tenant.id,
        organization_id=organization.id,
        name=name or f'Campaign-{uuid.uuid4().hex[:8]}',
        domain=domain or f'example-{uuid.uuid4().hex[:8]}.test',
    )
    session.add(campaign)
    session.flush()
    return campaign


def create_test_crawl_run(session: Session, campaign_id: str, tenant_id: str) -> str:
    crawl_run = CrawlRun(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        crawl_type='deep',
        status='completed',
        seed_url='https://example.test',
        pages_discovered=0,
        created_at=datetime.now(UTC),
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
    )
    session.add(crawl_run)
    session.commit()
    session.refresh(crawl_run)
    return crawl_run.id


def create_test_page(
    session: Session,
    tenant_id: str,
    campaign_id: str,
    url: str = 'https://example.com/page-1',
) -> str:
    page = Page(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        url=url,
    )
    session.add(page)
    session.commit()
    session.refresh(page)
    return page.id
