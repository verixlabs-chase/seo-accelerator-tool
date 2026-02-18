import os
os.environ["APP_ENV"] = "test"
if os.getenv("DATABASE_URL"):
    os.environ["POSTGRES_DSN"] = os.environ["DATABASE_URL"]

# THEN import anything else
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.db.session as db_session_module
import app.tasks.tasks as tasks_module
from app.core.passwords import hash_password
from app.db.base import Base
from app.db.session import get_db

from app.main import app
from app.models.authority import Backlink, BacklinkOpportunity, Citation, OutreachCampaign, OutreachContact  # noqa: F401
from app.models.competitor import Competitor, CompetitorPage, CompetitorRanking, CompetitorSignal  # noqa: F401
from app.models.content import ContentAsset, ContentQcEvent, EditorialCalendar, InternalLinkMap  # noqa: F401
from app.models.crawl import CrawlRun, TechnicalIssue  # noqa: F401
from app.models.entity import CompetitorEntity, EntityAnalysisRun, PageEntity  # noqa: F401
from app.models.intelligence import AnomalyEvent, CampaignMilestone, IntelligenceScore, StrategyRecommendation  # noqa: F401
from app.models.local import LocalHealthSnapshot, LocalProfile, Review, ReviewVelocitySnapshot  # noqa: F401
from app.models.rank import CampaignKeyword, KeywordCluster, Ranking, RankingSnapshot  # noqa: F401
from app.models.reference_library import (
    ReferenceLibraryActivation,  # noqa: F401
    ReferenceLibraryArtifact,  # noqa: F401
    ReferenceLibraryValidationRun,  # noqa: F401
    ReferenceLibraryVersion,  # noqa: F401
)
from app.models.reporting import MonthlyReport, ReportArtifact, ReportDeliveryEvent, ReportSchedule, ReportTemplateVersion  # noqa: F401
from app.models.role import Role, UserRole
from app.models.tenant import Tenant
from app.models.user import User


@pytest.fixture(scope="session", autouse=True)
def apply_migrations() -> None:
    backend_dir = Path(__file__).resolve().parents[1]
    database_url = os.getenv("DATABASE_URL", "").strip() or os.getenv("POSTGRES_DSN", "").strip() or "sqlite:///./test.db"
    os.environ["DATABASE_URL"] = database_url
    os.environ["POSTGRES_DSN"] = database_url

    from app.core.settings import get_settings

    get_settings.cache_clear()
    print(f"[tests] DATABASE_URL={database_url}")
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True, cwd=str(backend_dir))


@pytest.fixture()
def db_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    test_session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    test_session = test_session_local()

    # Ensure eager Celery tasks read/write against the same committed test DB.
    db_session_module.engine = engine
    db_session_module.SessionLocal = test_session_local
    tasks_module.SessionLocal = test_session_local

    tenant_a = Tenant(id=str(uuid.uuid4()), name="Tenant A", created_at=datetime.now(UTC))
    tenant_b = Tenant(id=str(uuid.uuid4()), name="Tenant B", created_at=datetime.now(UTC))
    role = Role(id="tenant_admin", name="tenant_admin", created_at=datetime.now(UTC))
    user_a = User(
        id=str(uuid.uuid4()),
        tenant_id=tenant_a.id,
        email="a@example.com",
        password_hash=hash_password("pass-a"),
        created_at=datetime.now(UTC),
        is_active=True,
    )
    user_b = User(
        id=str(uuid.uuid4()),
        tenant_id=tenant_b.id,
        email="b@example.com",
        password_hash=hash_password("pass-b"),
        created_at=datetime.now(UTC),
        is_active=True,
    )
    test_session.add_all([tenant_a, tenant_b, role, user_a, user_b])
    test_session.add_all(
        [
            UserRole(id=str(uuid.uuid4()), user_id=user_a.id, role_id=role.id, created_at=datetime.now(UTC)),
            UserRole(id=str(uuid.uuid4()), user_id=user_b.id, role_id=role.id, created_at=datetime.now(UTC)),
        ]
    )
    test_session.commit()
    yield test_session
    test_session.close()


@pytest.fixture()
def client(db_session: Session) -> TestClient:
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
