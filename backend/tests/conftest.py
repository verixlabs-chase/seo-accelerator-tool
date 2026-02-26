import os
os.environ["APP_ENV"] = "test"
if os.getenv("DATABASE_URL"):
    os.environ["POSTGRES_DSN"] = os.environ["DATABASE_URL"]

# THEN import anything else
import shutil
import tempfile
import time
import uuid
from datetime import UTC, datetime
from typing import Generator
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

import app.db.session as db_session_module
import app.tasks.tasks as tasks_module
from app.core.passwords import hash_password
from app.db.session import get_db

from app.models.authority import Backlink, BacklinkOpportunity, Citation, OutreachCampaign, OutreachContact  # noqa: F401
from app.models.competitor import Competitor, CompetitorPage, CompetitorRanking, CompetitorSignal  # noqa: F401
from app.models.content import ContentAsset, ContentQcEvent, EditorialCalendar, InternalLinkMap  # noqa: F401
from app.models.crawl import CrawlRun, TechnicalIssue  # noqa: F401
from app.models.entity import CompetitorEntity, EntityAnalysisRun, PageEntity  # noqa: F401
from app.models.intelligence import AnomalyEvent, CampaignMilestone, IntelligenceScore, StrategyRecommendation  # noqa: F401
from app.models.local import LocalHealthSnapshot, LocalProfile, Review, ReviewVelocitySnapshot  # noqa: F401
from app.models.organization import Organization  # noqa: F401
from app.models.organization_membership import OrganizationMembership  # noqa: F401
from app.models.organization_provider_credential import OrganizationProviderCredential  # noqa: F401
from app.models.platform_provider_credential import PlatformProviderCredential  # noqa: F401
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
from app.models.sub_account import SubAccount  # noqa: F401
from app.models.tenant import Tenant
from app.models.temporal import MomentumMetric, StrategyPhaseHistory, TemporalSignalSnapshot  # noqa: F401
from app.models.user import User



def _run_alembic_upgrade(backend_dir: Path, database_url: str) -> None:
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    os.environ["DATABASE_URL"] = database_url
    os.environ["POSTGRES_DSN"] = database_url
    command.upgrade(cfg, "head")


def pytest_configure(config: pytest.Config) -> None:
    workers = getattr(config.option, "numprocesses", None)
    if workers and int(workers) > 1:
        pytest.exit("SQLite test path does not support pytest-xdist parallel workers.")
@pytest.fixture(scope="session", autouse=True)
def apply_migrations() -> Generator[Path, None, None]:
    backend_dir = Path(__file__).resolve().parents[1]
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
    # Keep SQLite fast-lane aligned with migration head by asserting required tables exist.
    verification_engine = create_engine(database_url, connect_args={"check_same_thread": False, "timeout": 30}, poolclass=NullPool)
    try:
        has_crawl_runs = inspect(verification_engine).has_table("crawl_runs")
    finally:
        verification_engine.dispose()
    if not has_crawl_runs:
        raise RuntimeError("Alembic migration parity check failed; missing table: crawl_runs")
    yield template_db_path
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture(scope="session", autouse=True)
def bind_module_session_factories(apply_migrations: Path) -> Generator[None, None, None]:
    database_url = f"sqlite:///{apply_migrations.as_posix()}"
    bootstrap_engine = create_engine(database_url, connect_args={"check_same_thread": False, "timeout": 30}, poolclass=NullPool)
    bootstrap_session_local = sessionmaker(bind=bootstrap_engine, autocommit=False, autoflush=False)

    db_session_module.bind_session_factory_for_tests(bootstrap_session_local)

    import app.api.v1.crawl as crawl_api_module

    tasks_module.SessionLocal = db_session_module.SessionLocal
    crawl_api_module.SessionLocal = db_session_module.SessionLocal

    # Import app after rebinding to avoid stale SessionLocal capture in route modules.
    import app.main  # noqa: F401

    yield
    bootstrap_engine.dispose()


@pytest.fixture()
def db_session(apply_migrations: Path) -> Generator[Session, None, None]:
    test_db_path = apply_migrations.parent / f"{uuid.uuid4().hex}.sqlite3"
    shutil.copy2(apply_migrations, test_db_path)
    database_url = f"sqlite:///{test_db_path.as_posix()}"
    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False, "timeout": 30},
        poolclass=NullPool,
    )
    test_session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    test_session = test_session_local()

    # Ensure eager Celery tasks read/write against the same committed test DB.
    db_session_module.bind_session_factory_for_tests(test_session_local)
    tasks_module.SessionLocal = db_session_module.SessionLocal
    import app.api.v1.crawl as crawl_api_module

    crawl_api_module.SessionLocal = db_session_module.SessionLocal

    tenant_a = Tenant(id=str(uuid.uuid4()), name="Tenant A", created_at=datetime.now(UTC))
    tenant_b = Tenant(id=str(uuid.uuid4()), name="Tenant B", created_at=datetime.now(UTC))
    org_a = Organization(
        id=tenant_a.id,
        name=f"Org-{tenant_a.id[:8]}",
        plan_type="standard",
        billing_mode="subscription",
        status="active",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    org_b = Organization(
        id=tenant_b.id,
        name=f"Org-{tenant_b.id[:8]}",
        plan_type="standard",
        billing_mode="subscription",
        status="active",
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
    yield test_session
    test_session.close()
    engine.dispose()
    db_session_module.reset_engine_state()
    for _ in range(5):
        try:
            test_db_path.unlink(missing_ok=True)
            break
        except PermissionError:
            time.sleep(0.05)


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    from app.main import app

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


