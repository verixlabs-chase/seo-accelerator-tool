import uuid
from datetime import UTC, datetime

from app.models.role import Role, UserRole
from app.models.user import User


def _login(client, email, password):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def _grant_platform_admin(db_session, email: str) -> None:
    role = db_session.query(Role).filter(Role.id == "platform_admin").first()
    if role is None:
        role = Role(id="platform_admin", name="platform_admin", created_at=datetime.now(UTC))
        db_session.add(role)
        db_session.flush()
    user = db_session.query(User).filter(User.email == email).first()
    assert user is not None
    existing = (
        db_session.query(UserRole)
        .filter(UserRole.user_id == user.id, UserRole.role_id == role.id)
        .first()
    )
    if existing is None:
        db_session.add(UserRole(id=str(uuid.uuid4()), user_id=user.id, role_id=role.id, created_at=datetime.now(UTC)))
        db_session.commit()


def test_tenant_lifecycle_transition_guards(client, db_session):
    _grant_platform_admin(db_session, "a@example.com")
    token = _login(client, "a@example.com", "pass-a")
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post("/api/v1/tenants", json={"name": "Lifecycle Tenant"}, headers=headers)
    assert created.status_code == 200
    tenant_id = created.json()["data"]["id"]
    assert created.json()["data"]["status"] == "Active"

    invalid = client.patch(
        f"/api/v1/tenants/{tenant_id}/status",
        json={"target_status": "Archived"},
        headers=headers,
    )
    assert invalid.status_code == 400

    suspended = client.patch(
        f"/api/v1/tenants/{tenant_id}/status",
        json={"target_status": "Suspended"},
        headers=headers,
    )
    assert suspended.status_code == 200
    assert suspended.json()["data"]["status"] == "Suspended"


def test_campaign_setup_transition_guards(client):
    token = _login(client, "a@example.com", "pass-a")
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post(
        "/api/v1/campaigns",
        json={"name": "Lifecycle Campaign", "domain": "lifecycle.com"},
        headers=headers,
    )
    assert created.status_code == 200
    campaign_id = created.json()["data"]["id"]
    assert created.json()["data"]["setup_state"] == "Draft"

    invalid = client.patch(
        f"/api/v1/campaigns/{campaign_id}/setup-state",
        json={"target_state": "Active"},
        headers=headers,
    )
    assert invalid.status_code == 400

    configured = client.patch(
        f"/api/v1/campaigns/{campaign_id}/setup-state",
        json={"target_state": "Configured"},
        headers=headers,
    )
    assert configured.status_code == 200
    assert configured.json()["data"]["setup_state"] == "Configured"
