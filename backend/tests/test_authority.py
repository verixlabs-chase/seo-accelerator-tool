import pytest

from app.models.authority import Citation
from app.models.organization import Organization
from app.services import authority_service
from app.services.commercial_plan_service import apply_commercial_plan
from app.services.cost_economics_service import CostEconomicsError


def _login(client, email, password):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    payload = response.json()["data"]
    return payload["access_token"], payload["user"]["tenant_id"]


def test_authority_and_citation_endpoints(client, db_session):
    token, tenant_id = _login(client, "a@example.com", "pass-a")
    campaign = client.post(
        "/api/v1/campaigns",
        json={"name": "Authority Campaign", "domain": "authority.com"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]

    outreach = client.post(
        "/api/v1/authority/outreach-campaigns",
        json={"campaign_id": campaign["id"], "name": "Month 3 Outreach"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert outreach.status_code == 200
    outreach_id = outreach.json()["data"]["id"]
    assert outreach.json()["data"]["status"] == "draft"
    assert outreach.json()["data"]["manual_send_only"] is True

    contact = client.post(
        "/api/v1/authority/contacts",
        json={
            "campaign_id": campaign["id"],
            "outreach_campaign_id": outreach_id,
            "full_name": "Alex Partner",
            "email": "alex@example.com",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert contact.status_code == 200
    assert contact.json()["data"]["status"] == "draft"
    assert contact.json()["data"]["manual_send_only"] is True

    backlinks = client.get(
        f"/api/v1/authority/backlinks?campaign_id={campaign['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert backlinks.status_code == 200
    assert len(backlinks.json()["data"]["items"]) >= 1

    citation_submit = client.post(
        "/api/v1/citations/submissions",
        json={"campaign_id": campaign["id"], "directory_name": "Yelp"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert citation_submit.status_code == 403
    assert (
        citation_submit.json()["errors"][0]["details"]["reason_code"]
        == "listing_correction_sync_upgrade_required"
    )
    assert db_session.query(Citation).count() == 0

    organization = db_session.get(Organization, tenant_id)
    assert organization is not None
    apply_commercial_plan(
        db_session,
        organization_id=organization.id,
        plan_code="multi_location",
    )
    db_session.commit()
    eligible_but_unavailable = client.post(
        "/api/v1/citations/submissions",
        json={"campaign_id": campaign["id"], "directory_name": "Yelp"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert eligible_but_unavailable.status_code == 409
    assert (
        eligible_but_unavailable.json()["errors"][0]["details"]["reason_code"]
        == "listing_correction_provider_not_approved"
    )
    assert db_session.query(Citation).count() == 0

    citation_status = client.get(
        f"/api/v1/citations/status?campaign_id={campaign['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert citation_status.status_code == 200
    status_data = citation_status.json()["data"]
    assert status_data["job_id"] is None
    assert status_data["items"] == []
    assert status_data["truth"]["classification"] == "unavailable"
    assert status_data["correction_access"]["plan_eligible"] is True
    assert status_data["correction_access"]["correction_enabled"] is False
    assert status_data["correction_access"]["state"] == "provider_approval_required"

    saved_history = Citation(
        tenant_id=tenant_id,
        campaign_id=campaign["id"],
        directory_name="Legacy directory",
        submission_status="draft",
    )
    db_session.add(saved_history)
    db_session.commit()

    with pytest.raises(CostEconomicsError) as submit_job_denied:
        authority_service.submit_citation_batch(
            db_session,
            tenant_id=tenant_id,
            campaign_id=campaign["id"],
        )
    assert submit_job_denied.value.reason_code == "listing_correction_provider_not_approved"

    with pytest.raises(CostEconomicsError) as refresh_job_denied:
        authority_service.refresh_citation_status(
            db_session,
            tenant_id=tenant_id,
            campaign_id=campaign["id"],
        )
    assert refresh_job_denied.value.reason_code == "listing_correction_provider_not_approved"
    db_session.refresh(saved_history)
    assert saved_history.submission_status == "draft"
