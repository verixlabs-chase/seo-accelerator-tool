import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.passwords import hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.competitor import Competitor, CompetitorPage, CompetitorRanking, CompetitorSignal  # noqa: F401
from app.models.crawl import CrawlRun, TechnicalIssue  # noqa: F401
from app.models.rank import CampaignKeyword, KeywordCluster, Ranking, RankingSnapshot  # noqa: F401
from app.models.role import Role, UserRole
from app.models.tenant import Tenant
from app.models.user import User


@pytest.fixture()
def db_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    test_session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
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
