from pathlib import Path

from app.models.enterprise_client_invitation import EnterpriseClientInvitation


def test_enterprise_client_invitation_migration_matches_secure_model_contract() -> None:
    migration = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260820_0202_enterprise_client_invitations.py"
    ).read_text(encoding="utf-8")

    assert 'revision = "20260820_0202"' in migration
    assert 'down_revision = "20260820_0201"' in migration
    for column_name in EnterpriseClientInvitation.__table__.columns.keys():
        assert f'"{column_name}"' in migration
    assert "tenant_id = organization_id" in migration
    assert "fk_enterprise_client_invites_group_org" in migration
    assert "uq_enterprise_client_invites_org_email_group" in migration
    assert "uq_enterprise_client_invites_token_hash" in migration
    assert "ENABLE ROW LEVEL SECURITY" in migration
    assert "current_organization_id" in migration
    assert "app.platform_access" in migration
    assert "REVOKE DELETE" in migration
    assert "Cannot downgrade while Enterprise client invitations exist" in migration
