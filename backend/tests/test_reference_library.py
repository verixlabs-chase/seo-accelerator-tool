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


def test_reference_library_requires_platform_admin(client):
    token = _login(client, "a@example.com", "pass-a")
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post(
        "/api/v1/reference-library/validate",
        json={"version": "0.1.0", "strict_mode": True},
        headers=headers,
    )
    assert response.status_code == 403


def test_reference_library_validate_activate_and_read(client, db_session):
    _grant_platform_admin(db_session, "a@example.com")
    token = _login(client, "a@example.com", "pass-a")
    headers = {"Authorization": f"Bearer {token}"}

    validated = client.post(
        "/api/v1/reference-library/validate",
        json={"version": "0.1.0", "strict_mode": True},
        headers=headers,
    )
    assert validated.status_code == 200
    payload = validated.json()["data"]
    assert payload["status"] == "passed"
    assert payload["errors"] == []

    activated = client.post(
        "/api/v1/reference-library/activate",
        json={"version": "0.1.0", "reason": "bootstrap"},
        headers=headers,
    )
    assert activated.status_code == 200
    assert activated.json()["data"]["status"] == "active"

    versions = client.get("/api/v1/reference-library/versions", headers=headers)
    assert versions.status_code == 200
    items = versions.json()["data"]["items"]
    assert any(item["version"] == "0.1.0" and item["status"] == "active" for item in items)

    active = client.get("/api/v1/reference-library/active", headers=headers)
    assert active.status_code == 200
    assert active.json()["data"]["version"] == "0.1.0"


def test_reference_library_activation_blocked_if_latest_validation_failed(client, db_session):
    _grant_platform_admin(db_session, "a@example.com")
    token = _login(client, "a@example.com", "pass-a")
    headers = {"Authorization": f"Bearer {token}"}

    invalid_artifacts = {
        "metrics": {
            "_meta": {"purpose": "bad", "version": "0.1.1", "generated_at": "2026-02-18T00:00:00Z"},
            "metrics": [
                {
                    "metric_key": "cwv_lcp",
                    "thresholds": {"good": 2500, "needs_improvement": 4000, "units": "ms"},
                    "recommendations": ["missing_rec_key"],
                }
            ],
        },
        "recommendations": {
            "_meta": {"purpose": "bad", "version": "0.1.1", "generated_at": "2026-02-18T00:00:00Z"},
            "recommendations": [],
        },
    }

    validated = client.post(
        "/api/v1/reference-library/validate",
        json={"version": "0.1.1", "strict_mode": True, "artifacts": invalid_artifacts},
        headers=headers,
    )
    assert validated.status_code == 200
    assert validated.json()["data"]["status"] == "failed"

    activate = client.post(
        "/api/v1/reference-library/activate",
        json={"version": "0.1.1", "reason": "should_fail"},
        headers=headers,
    )
    assert activate.status_code == 409
    payload = activate.json()
    assert payload["success"] is False
    assert "not PASSED" in payload["errors"][0]["message"]
