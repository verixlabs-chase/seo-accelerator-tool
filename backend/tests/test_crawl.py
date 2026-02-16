from datetime import UTC, datetime

from app.models.campaign import Campaign
from app.models.crawl import CrawlRun, TechnicalIssue
from app.models.user import User


def _login(client, email, password):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def test_crawl_schedule_and_runs(client):
    token = _login(client, "a@example.com", "pass-a")
    campaign = client.post(
        "/api/v1/campaigns",
        json={"name": "Crawler Campaign", "domain": "example.com"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]

    scheduled = client.post(
        "/api/v1/crawl/schedule",
        json={"campaign_id": campaign["id"], "crawl_type": "deep", "seed_url": "https://example.com"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert scheduled.status_code == 200
    assert scheduled.json()["data"]["status"] == "scheduled"

    runs = client.get("/api/v1/crawl/runs", headers={"Authorization": f"Bearer {token}"})
    assert runs.status_code == 200
    assert len(runs.json()["data"]["items"]) == 1
    assert runs.json()["data"]["items"][0]["campaign_id"] == campaign["id"]


def test_crawl_issues_tenant_isolation(client, db_session):
    user_a = db_session.query(User).filter(User.email == "a@example.com").first()
    user_b = db_session.query(User).filter(User.email == "b@example.com").first()
    assert user_a is not None
    assert user_b is not None

    campaign_a = Campaign(tenant_id=user_a.tenant_id, name="A Crawl", domain="a.com")
    campaign_b = Campaign(tenant_id=user_b.tenant_id, name="B Crawl", domain="b.com")
    db_session.add_all([campaign_a, campaign_b])
    db_session.flush()

    run_a = CrawlRun(
        tenant_id=user_a.tenant_id,
        campaign_id=campaign_a.id,
        crawl_type="deep",
        status="complete",
        seed_url="https://a.com",
        created_at=datetime.now(UTC),
    )
    run_b = CrawlRun(
        tenant_id=user_b.tenant_id,
        campaign_id=campaign_b.id,
        crawl_type="deep",
        status="complete",
        seed_url="https://b.com",
        created_at=datetime.now(UTC),
    )
    db_session.add_all([run_a, run_b])
    db_session.flush()

    issue_a = TechnicalIssue(
        tenant_id=user_a.tenant_id,
        campaign_id=campaign_a.id,
        crawl_run_id=run_a.id,
        page_id=None,
        issue_code="missing_title",
        severity="high",
        details_json="{}",
    )
    issue_b = TechnicalIssue(
        tenant_id=user_b.tenant_id,
        campaign_id=campaign_b.id,
        crawl_run_id=run_b.id,
        page_id=None,
        issue_code="missing_meta_description",
        severity="medium",
        details_json="{}",
    )
    db_session.add_all([issue_a, issue_b])
    db_session.commit()

    token_a = _login(client, "a@example.com", "pass-a")
    response = client.get("/api/v1/crawl/issues", headers={"Authorization": f"Bearer {token_a}"})
    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["issue_code"] == "missing_title"

