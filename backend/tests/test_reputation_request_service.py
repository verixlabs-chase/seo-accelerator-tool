from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import inspect

from app.models.business_location import BusinessLocation
from app.models.campaign import Campaign
from app.models.data_connection import DataConnection
from app.models.google_business_profile import GoogleBusinessProfileSnapshot
from app.models.organization_membership import OrganizationMembership
from app.models.user import User
from app.services import reputation_request_service


NOW = datetime(2026, 8, 10, 18, 0, tzinfo=UTC)
REVIEW_URL = "https://g.page/r/test-location/review"


def _connected_campaign(db_session) -> tuple[User, Campaign]:
    user = db_session.query(User).filter(User.email == "a@example.com").one()
    membership = (
        db_session.query(OrganizationMembership)
        .filter(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.status == "active",
        )
        .one()
    )
    location = BusinessLocation(
        organization_id=membership.organization_id,
        name="Junk Magicians Reno",
        domain="junkmagiciansnv.com",
        city="Reno",
        region="NV",
        country_code="US",
        status="active",
        created_at=NOW,
        updated_at=NOW,
    )
    db_session.add(location)
    db_session.flush()
    campaign = Campaign(
        tenant_id=user.tenant_id,
        organization_id=membership.organization_id,
        business_location_id=location.id,
        name="Reno Local SEO",
        domain=location.domain,
        setup_state="Active",
        created_at=NOW,
    )
    db_session.add(campaign)
    db_session.flush()
    connection = DataConnection(
        tenant_id=user.tenant_id,
        organization_id=membership.organization_id,
        business_location_id=location.id,
        campaign_id=campaign.id,
        provider_name="google_business_profile",
        external_resource_id="locations/123",
        external_resource_name=location.name,
        resource_scope="owned_business_profile",
        status="connected",
        sync_cursor={},
        connection_metadata={},
        created_by_user_id=user.id,
        created_at=NOW,
        updated_at=NOW,
    )
    db_session.add(connection)
    db_session.flush()
    db_session.add(
        GoogleBusinessProfileSnapshot(
            connection_id=connection.id,
            tenant_id=user.tenant_id,
            organization_id=membership.organization_id,
            campaign_id=campaign.id,
            business_location_id=location.id,
            external_resource_id=connection.external_resource_id,
            profile_hash="a" * 64,
            profile_data={"metadata": {"newReviewUri": REVIEW_URL}},
            audit_summary={},
            metric_contract_id="gbp.profile.configuration",
            metric_contract_version="1.0",
            source_account_id="accounts/1",
            scope_key="test",
            captured_at=NOW,
        )
    )
    db_session.commit()
    return user, campaign


def _create(db_session, user: User, campaign: Campaign, *, channel: str = "link", body: str = ""):
    return reputation_request_service.create_campaign(
        db_session,
        tenant_id=user.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
        user_id=user.id,
        name="Recent customer requests",
        channel=channel,
        subject=None,
        message_body=body,
        review_url=None,
    )


def test_link_campaign_uses_connected_review_url_and_never_filters_by_rating(db_session):
    user, campaign = _connected_campaign(db_session)

    result = _create(db_session, user, campaign)

    assert result["channel"] == "link"
    assert result["status"] == "active"
    assert result["review_url"] == REVIEW_URL
    assert result["review_url_source"] == "connected_profile"
    assert result["audience_rule"] == {
        "eligibility": "all_confirmed_eligible_customers",
        "service_completion_required": True,
        "rating_or_satisfaction_filter_allowed": False,
    }
    assert REVIEW_URL in result["message_body"]
    assert result["result_summary"]["attribution_state"] == "time_window_only"
    assert "does not claim" in result["result_summary"]["note"]


def test_review_gating_language_and_sms_fail_closed(db_session):
    user, campaign = _connected_campaign(db_session)

    with pytest.raises(HTTPException) as gating_error:
        _create(
            db_session,
            user,
            campaign,
            body="If you had a good experience, leave us a five-star review.",
        )
    assert gating_error.value.status_code == 400

    with pytest.raises(HTTPException) as sms_error:
        _create(db_session, user, campaign, channel="sms")
    assert sms_error.value.status_code == 409
    assert "own provider" in str(sms_error.value.detail)


def test_email_recipients_require_consent_and_suppression_applies_across_campaigns(db_session):
    user, campaign = _connected_campaign(db_session)
    first = _create(db_session, user, campaign, channel="email")
    assert first["status"] == "draft"

    with pytest.raises(HTTPException) as consent_error:
        reputation_request_service.add_recipient(
            db_session,
            tenant_id=user.tenant_id,
            organization_id=str(campaign.organization_id),
            request_campaign_id=first["id"],
            email_address="customer@example.com",
            customer_name="Customer",
            consent_basis="existing_customer_relationship",
            consent_source="Completed invoice",
            consent_confirmed=False,
            service_completed_at=NOW - timedelta(days=1),
        )
    assert consent_error.value.status_code == 400

    recipient = reputation_request_service.add_recipient(
        db_session,
        tenant_id=user.tenant_id,
        organization_id=str(campaign.organization_id),
        request_campaign_id=first["id"],
        email_address="customer@example.com",
        customer_name="Customer",
        consent_basis="existing_customer_relationship",
        consent_source="Completed invoice",
        consent_confirmed=True,
        service_completed_at=NOW - timedelta(days=1),
    )
    assert recipient["status"] == "eligible"
    assert recipient["email"] != "customer@example.com"

    suppressed = reputation_request_service.suppress_recipient(
        db_session,
        tenant_id=user.tenant_id,
        organization_id=str(campaign.organization_id),
        recipient_id=recipient["id"],
        reason="Customer opted out",
        source="Account owner",
    )
    assert suppressed["status"] == "suppressed"

    second = _create(db_session, user, campaign, channel="email")
    future_recipient = reputation_request_service.add_recipient(
        db_session,
        tenant_id=user.tenant_id,
        organization_id=str(campaign.organization_id),
        request_campaign_id=second["id"],
        email_address="customer@example.com",
        customer_name="Customer",
        consent_basis="existing_customer_relationship",
        consent_source="Completed invoice",
        consent_confirmed=True,
        service_completed_at=NOW - timedelta(days=1),
    )
    assert future_recipient["status"] == "suppressed"
    assert future_recipient["suppression_reason"] == "Customer opted out"


def test_live_email_activation_is_blocked_while_adapter_is_synthetic(db_session):
    user, campaign = _connected_campaign(db_session)
    request_campaign = _create(db_session, user, campaign, channel="email")

    with pytest.raises(HTTPException) as exc:
        reputation_request_service.control_campaign(
            db_session,
            tenant_id=user.tenant_id,
            organization_id=str(campaign.organization_id),
            request_campaign_id=request_campaign["id"],
            action="activate",
        )

    assert exc.value.status_code == 409
    assert "verified transactional email provider" in str(exc.value.detail)


def test_review_request_api_lists_plain_language_channel_truth(client, db_session):
    _user, campaign = _connected_campaign(db_session)
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "a@example.com", "password": "pass-a"},
    )
    token = login.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    created = client.post(
        "/api/v1/reviews/request-campaigns",
        headers=headers,
        json={
            "campaign_id": campaign.id,
            "name": "Recent customers",
            "channel": "link",
            "message_body": "Would you share an honest review?",
        },
    )
    listed = client.get(
        f"/api/v1/reviews/request-campaigns?campaign_id={campaign.id}",
        headers=headers,
    )
    readiness = client.get("/api/v1/reviews/request-readiness", headers=headers)

    assert created.status_code == 200
    assert listed.status_code == 200
    assert len(listed.json()["data"]["items"]) == 1
    assert readiness.json()["data"]["channels"]["link"]["available"] is True
    assert readiness.json()["data"]["channels"]["email"]["available"] is False
    serialized = str(created.json()).lower()
    assert "dataforseo" not in serialized
    assert "provider_name" not in serialized
    assert "rating_or_satisfaction_filter_allowed': true" not in serialized


def test_review_request_migration_creates_governed_tables(db_session):
    tables = set(inspect(db_session.get_bind()).get_table_names())
    assert {
        "reputation_review_request_campaigns",
        "reputation_review_request_recipients",
        "reputation_review_request_suppressions",
        "reputation_review_request_deliveries",
    }.issubset(tables)
