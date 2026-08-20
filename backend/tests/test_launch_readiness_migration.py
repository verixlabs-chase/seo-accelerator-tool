from pathlib import Path

from app.models.customer_status import CustomerStatusUpdate
from app.models.launch_readiness import LaunchReadinessDecision, LaunchReadinessProof
from app.models.launch_experience import LaunchExperienceReview
from app.models.production_capability import ProductionCapabilityProof


def test_launch_readiness_proof_model_and_migration_are_append_only() -> None:
    backend = Path(__file__).resolve().parents[1]
    migration = (
        backend / "alembic/versions/20260820_0203_launch_readiness_proofs.py"
    ).read_text(encoding="utf-8")

    assert LaunchReadinessProof.__tablename__ == "launch_readiness_proofs"
    assert 'revision = "20260820_0203"' in migration
    assert 'down_revision = "20260820_0202"' in migration
    assert "GRANT SELECT, INSERT" in migration
    assert "REVOKE UPDATE, DELETE" in migration
    assert "app.platform_access" in migration
    assert "launch readiness proofs are append-only and immutable" in migration
    assert "Cannot downgrade while launch readiness proof history exists" in migration


def test_launch_readiness_decision_model_and_migration_are_append_only() -> None:
    backend = Path(__file__).resolve().parents[1]
    migration = (
        backend / "alembic/versions/20260820_0204_launch_readiness_decisions.py"
    ).read_text(encoding="utf-8")

    assert LaunchReadinessDecision.__tablename__ == "launch_readiness_decisions"
    assert 'revision = "20260820_0204"' in migration
    assert 'down_revision = "20260820_0203"' in migration
    assert "GRANT SELECT, INSERT" in migration
    assert "REVOKE UPDATE, DELETE" in migration
    assert "app.platform_access" in migration
    assert "launch readiness decisions are append-only and immutable" in migration
    assert "Cannot downgrade while launch decision history exists" in migration


def test_customer_status_model_and_migration_are_append_only_and_customer_readable() -> None:
    backend = Path(__file__).resolve().parents[1]
    migration = (
        backend / "alembic/versions/20260820_0205_customer_status_updates.py"
    ).read_text(encoding="utf-8")

    assert CustomerStatusUpdate.__tablename__ == "customer_status_updates"
    assert 'revision = "20260820_0205"' in migration
    assert 'down_revision = "20260820_0204"' in migration
    assert "GRANT SELECT, INSERT" in migration
    assert "REVOKE UPDATE, DELETE" in migration
    assert "visible_to_customers OR" in migration
    assert "app.platform_access" in migration
    assert "customer status updates are append-only and immutable" in migration
    assert "Cannot downgrade while customer status history exists" in migration


def test_production_capability_proof_model_and_migration_are_platform_only() -> None:
    backend = Path(__file__).resolve().parents[1]
    migration = (
        backend / "alembic/versions/20260820_0206_production_capability_proofs.py"
    ).read_text(encoding="utf-8")

    assert ProductionCapabilityProof.__tablename__ == "production_capability_proofs"
    assert 'revision = "20260820_0206"' in migration
    assert 'down_revision = "20260820_0205"' in migration
    assert "GRANT SELECT, INSERT" in migration
    assert "REVOKE UPDATE, DELETE" in migration
    assert "app.platform_access" in migration
    assert "production capability proofs are append-only and immutable" in migration
    assert "Cannot downgrade while production capability proof history exists" in migration


def test_launch_experience_review_model_and_migration_are_append_only() -> None:
    backend = Path(__file__).resolve().parents[1]
    migration = (
        backend / "alembic/versions/20260820_0207_launch_experience_reviews.py"
    ).read_text(encoding="utf-8")

    assert LaunchExperienceReview.__tablename__ == "launch_experience_reviews"
    assert 'revision = "20260820_0207"' in migration
    assert 'down_revision = "20260820_0206"' in migration
    assert "GRANT SELECT, INSERT" in migration
    assert "REVOKE UPDATE, DELETE" in migration
    assert "app.platform_access" in migration
    assert "launch experience reviews are append-only and immutable" in migration
    assert "Cannot downgrade while launch experience review history exists" in migration
