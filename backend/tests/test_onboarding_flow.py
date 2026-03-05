import uuid

from app.models.campaign import Campaign
from app.services import onboarding_service

MASTER_KEY_B64 = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


def _login(client, email: str = "a@example.com", password: str = "pass-a") -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _payload(suffix: str, *, automation_override: bool = True) -> dict:
    return {
        "tenant_name": f"Onboarding Tenant {suffix}",
        "organization_name": f"Onboarding Org {suffix}",
        "campaign_name": f"Onboarding Campaign {suffix}",
        "campaign_domain": "onboarding.example",
        "provider_name": "google",
        "provider_auth_mode": "api_key",
        "provider_credentials": {"api_key": "test-key"},
        "crawl_type": "deep",
        "crawl_seed_url": "https://example.com",
        "report_month_number": 1,
        "automation_override": automation_override,
    }


def test_onboarding_happy_path(client, db_session, monkeypatch):
    monkeypatch.setenv("PLATFORM_MASTER_KEY", MASTER_KEY_B64)
    monkeypatch.setattr("app.services.onboarding_service._dispatch_crawl_task", lambda *_args, **_kwargs: "task-1")
    token = _login(client)
    response = client.post("/api/v1/onboarding/start", json=_payload(str(uuid.uuid4())), headers=_headers(token))
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "COMPLETED"
    assert data["current_step"] == "COMPLETED"
    assert data["tenant_id"]
    assert data["organization_id"] == data["tenant_id"]
    assert data["campaign_id"]

    campaign = db_session.get(Campaign, data["campaign_id"])
    assert campaign is not None
    assert campaign.setup_state == "Active"


def test_onboarding_failure_then_resume(client, monkeypatch):
    monkeypatch.setenv("PLATFORM_MASTER_KEY", MASTER_KEY_B64)
    monkeypatch.setattr("app.services.onboarding_service._dispatch_crawl_task", lambda *_args, **_kwargs: "task-2")
    token = _login(client)
    calls = {"count": 0}
    original = onboarding_service.provider_credentials_service.upsert_organization_provider_credentials

    def _flaky(*args, **kwargs):
        if calls["count"] == 0:
            calls["count"] += 1
            raise RuntimeError("provider bootstrap failed")
        return original(*args, **kwargs)

    monkeypatch.setattr("app.services.onboarding_service.provider_credentials_service.upsert_organization_provider_credentials", _flaky)

    start = client.post("/api/v1/onboarding/start", json=_payload(str(uuid.uuid4())), headers=_headers(token))
    assert start.status_code == 200
    start_data = start.json()["data"]
    assert start_data["status"] == "FAILED"
    assert start_data["current_step"] == "FAILED"
    assert start_data["error_state"]["step"] == "PROVIDER_CONNECTED"
    tenant_id = start_data["tenant_id"]

    resume = client.post(f"/api/v1/onboarding/resume/{tenant_id}", headers=_headers(token))
    assert resume.status_code == 200
    resume_data = resume.json()["data"]
    assert resume_data["status"] == "COMPLETED"
    assert resume_data["current_step"] == "COMPLETED"


def test_onboarding_start_is_idempotent(client, db_session, monkeypatch):
    monkeypatch.setenv("PLATFORM_MASTER_KEY", MASTER_KEY_B64)
    monkeypatch.setattr("app.services.onboarding_service._dispatch_crawl_task", lambda *_args, **_kwargs: "task-3")
    token = _login(client)
    payload = _payload(str(uuid.uuid4()))

    first = client.post("/api/v1/onboarding/start", json=payload, headers=_headers(token))
    second = client.post("/api/v1/onboarding/start", json=payload, headers=_headers(token))

    assert first.status_code == 200
    assert second.status_code == 200
    first_data = first.json()["data"]
    second_data = second.json()["data"]
    assert first_data["id"] == second_data["id"]

    campaigns = (
        db_session.query(Campaign)
        .filter(
            Campaign.tenant_id == first_data["tenant_id"],
            Campaign.name == payload["campaign_name"],
            Campaign.domain == payload["campaign_domain"],
        )
        .all()
    )
    assert len(campaigns) == 1


def test_onboarding_campaign_setup_state_transitions(client, db_session, monkeypatch):
    monkeypatch.setenv("PLATFORM_MASTER_KEY", MASTER_KEY_B64)
    monkeypatch.setattr("app.services.onboarding_service._dispatch_crawl_task", lambda *_args, **_kwargs: "task-4")
    token = _login(client)
    payload = _payload(str(uuid.uuid4()))
    original = onboarding_service._ensure_report_generated
    calls = {"count": 0}

    def _fail_once(db, session, state_payload):
        if calls["count"] == 0:
            calls["count"] += 1
            raise RuntimeError("report pipeline unavailable")
        return original(db, session, state_payload)

    monkeypatch.setattr("app.services.onboarding_service._ensure_report_generated", _fail_once)
    start = client.post("/api/v1/onboarding/start", json=payload, headers=_headers(token))
    assert start.status_code == 200
    start_data = start.json()["data"]
    assert start_data["status"] == "FAILED"
    assert start_data["error_state"]["step"] == "REPORT_GENERATED"

    campaign = db_session.get(Campaign, start_data["campaign_id"])
    assert campaign is not None
    assert campaign.setup_state == "BaselineRunning"

    resume = client.post(f"/api/v1/onboarding/resume/{start_data['tenant_id']}", headers=_headers(token))
    assert resume.status_code == 200
    resume_data = resume.json()["data"]
    assert resume_data["status"] == "COMPLETED"

    campaign = db_session.get(Campaign, start_data["campaign_id"])
    assert campaign is not None
    assert campaign.setup_state == "Active"
