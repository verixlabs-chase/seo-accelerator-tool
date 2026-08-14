from __future__ import annotations

import json
import uuid

from app.models.ai_visibility import (
    AISearchCollectionRun,
    AISearchProviderContractRegistry,
    AISearchQuestionSet,
)
from app.models.business_location import BusinessLocation
from app.models.business_service import BusinessService
from app.models.business_service_area import BusinessServiceArea
from app.models.campaign import Campaign
from app.models.cost_economics import CostLedgerEntry
from app.models.organization_membership import OrganizationMembership
from app.models.user import User


def _login(client, email: str, password: str) -> tuple[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    user = response.json()["data"]["user"]
    return response.json()["data"]["access_token"], user["organization_id"]


def _campaign_with_context(db_session, organization_id: str) -> Campaign:
    location = BusinessLocation(
        organization_id=organization_id,
        name=f"Reno-{uuid.uuid4().hex[:8]}",
        domain="example.test",
        city="Reno",
        region="Nevada",
        country_code="US",
        status="active",
    )
    db_session.add(location)
    db_session.flush()
    campaign = Campaign(
        tenant_id=organization_id,
        organization_id=organization_id,
        business_location_id=location.id,
        name=f"Campaign-{uuid.uuid4().hex[:8]}",
        domain="example.test",
    )
    db_session.add(campaign)
    db_session.flush()
    db_session.add(
        BusinessService(
            tenant_id=organization_id,
            organization_id=organization_id,
            business_location_id=location.id,
            scope_type="location",
            scope_key=location.id,
            name="Junk removal",
            normalized_name="junk removal",
            aliases=[],
            status="confirmed",
            source="manual",
            confidence=1.0,
            evidence=[],
        )
    )
    db_session.add(
        BusinessServiceArea(
            tenant_id=organization_id,
            organization_id=organization_id,
            business_location_id=location.id,
            area_type="city",
            name="Reno",
            normalized_name="reno",
            region="Nevada",
            country_code="US",
            relationship="included",
            status="confirmed",
            source="manual",
            confidence=1.0,
            evidence=[],
        )
    )
    db_session.commit()
    return campaign


def test_ai_search_empty_state_and_frozen_question_api(client, db_session) -> None:
    token, organization_id = _login(client, "org-admin@example.com", "pass-org-admin")
    headers = {"Authorization": f"Bearer {token}"}
    campaign = _campaign_with_context(db_session, organization_id)

    engines = client.get("/api/v1/ai-search/engines", headers=headers)
    assert engines.status_code == 200
    assert engines.json()["data"]["truth_state"] == "unavailable"
    assert engines.json()["data"]["items"] == []
    assert "collection_method" not in json.dumps(engines.json())

    before = client.get(
        f"/api/v1/ai-search/summary?campaign_id={campaign.id}", headers=headers
    )
    assert before.status_code == 200
    before_data = before.json()["data"]
    assert set(before_data) == {
        "campaign_id",
        "business_location_id",
        "truth",
        "setup",
        "summary",
        "engines",
        "questions",
        "history",
        "competitors",
        "next_action",
        "limitations",
    }
    assert before_data["truth"]["state"] == "unavailable"
    assert before_data["setup"]["ready"] is True
    assert before_data["summary"]["sample_size"] == 0
    assert before_data["next_action"]["code"] == "save_questions"

    created = client.post(
        f"/api/v1/ai-search/question-sets?campaign_id={campaign.id}", headers=headers
    )
    assert created.status_code == 200
    created_data = created.json()["data"]
    assert created_data["created"] is True
    assert created_data["current_context"] is True
    assert created_data["collection_state"] == "unavailable"
    assert created_data["question_set"]["questions"][0]["text"] == (
        "Which businesses provide Junk removal in Reno, Nevada?"
    )

    current = client.get(
        f"/api/v1/ai-search/question-sets/current?campaign_id={campaign.id}",
        headers=headers,
    )
    assert current.status_code == 200
    assert current.json()["data"]["question_set"]["id"] == created_data["question_set"]["id"]
    encoded = json.dumps(current.json()).casefold()
    internal_supplier = "".join(("data", "for", "seo"))
    assert internal_supplier not in encoded
    assert "task_id" not in encoded


def test_org_user_can_save_deterministic_question_set(client, db_session) -> None:
    user = db_session.query(User).filter(User.email == "org-admin@example.com").one()
    membership = (
        db_session.query(OrganizationMembership)
        .filter(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.status == "active",
        )
        .one()
    )
    membership.role = "org_user"
    db_session.commit()
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "org-admin@example.com", "password": "pass-org-admin"},
    )
    assert login.status_code == 200
    assert login.json()["data"]["user"]["org_role"] == "org_user"
    token = login.json()["data"]["access_token"]
    organization_id = login.json()["data"]["user"]["organization_id"]
    campaign = _campaign_with_context(db_session, organization_id)

    response = client.post(
        f"/api/v1/ai-search/question-sets?campaign_id={campaign.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["created"] is True
    assert response.json()["data"]["question_set"]["question_count"] == 1
    repeated = client.post(
        f"/api/v1/ai-search/question-sets?campaign_id={campaign.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert repeated.status_code == 200
    assert repeated.json()["data"]["created"] is False
    assert repeated.json()["data"]["question_set"]["id"] == response.json()["data"][
        "question_set"
    ]["id"]


def test_ai_search_preview_is_fail_closed_side_effect_free_and_redacted(
    client,
    db_session,
) -> None:
    token, organization_id = _login(client, "org-admin@example.com", "pass-org-admin")
    headers = {"Authorization": f"Bearer {token}"}
    campaign = _campaign_with_context(db_session, organization_id)
    private_supplier = "internal-sensitive-supplier"
    db_session.add(
        AISearchProviderContractRegistry(
            provider_key=private_supplier,
            contract_code="private-candidate",
            contract_version="1",
            collection_mode="fixture",
            request_schema_version="1",
            response_schema_version="1",
            parser_version="parser-v1",
            normalizer_version="normalizer-v1",
            engine_mappings=[],
            required_inputs=[],
            guaranteed_evidence_facts=[],
            optional_evidence_facts=[],
            unsupported_evidence_facts=[],
            raw_response_retention_days=0,
            billable_unit="fixture",
            status="candidate",
            production_qa_passed=False,
            pricing_qa_passed=False,
            automatic_activation_allowed=False,
            content_hash=uuid.uuid4().hex * 2,
        )
    )
    db_session.commit()
    counts_before = {
        "question_sets": db_session.query(AISearchQuestionSet).count(),
        "runs": db_session.query(AISearchCollectionRun).count(),
        "ledger": db_session.query(CostLedgerEntry).count(),
    }

    engines = client.get("/api/v1/ai-search/engines", headers=headers)
    summary = client.get(
        f"/api/v1/ai-search/summary?campaign_id={campaign.id}", headers=headers
    )
    preview = client.post(
        f"/api/v1/ai-search/checks/preview?campaign_id={campaign.id}",
        headers=headers,
    )
    assert engines.status_code == summary.status_code == preview.status_code == 200
    preview_data = preview.json()["data"]
    assert preview_data["state"] == "unavailable"
    assert preview_data["ready"] is False
    assert preview_data["estimated_credits"] is None
    assert preview_data["checks"] == {
        "business_context_ready": True,
        "question_set_current": False,
        "approved_engine_available": False,
        "evidence_collection_ready": False,
        "cost_rules_configured": False,
        "usage_allowance_configured": False,
    }
    assert {item["code"] for item in preview_data["blockers"]} == {
        "questions_not_saved",
        "engine_checks_incomplete",
        "evidence_collection_not_ready",
        "cost_rules_not_ready",
        "usage_allowance_not_ready",
    }
    assert preview_data["side_effects"] == {
        "external_request_sent": False,
        "reservation_created": False,
        "charge_created": False,
        "run_created": False,
    }
    counts_after = {
        "question_sets": db_session.query(AISearchQuestionSet).count(),
        "runs": db_session.query(AISearchCollectionRun).count(),
        "ledger": db_session.query(CostLedgerEntry).count(),
    }
    assert counts_after == counts_before

    public_payloads = [
        engines.json()["data"],
        summary.json()["data"],
        preview_data,
    ]
    encoded = json.dumps(public_payloads).casefold()
    forbidden = {
        "provider_key",
        private_supplier,
        "task_id",
        "provider_task_id",
        "provider_request_id",
        "raw_response",
        "safe_error",
        "price_card_id",
        "cost_reservation_id",
        "credential_owner",
    }
    assert all(item not in encoded for item in forbidden)


def test_ai_search_campaign_lookup_is_tenant_and_organization_scoped(
    client,
    db_session,
) -> None:
    _token_a, organization_a = _login(client, "org-admin@example.com", "pass-org-admin")
    campaign = _campaign_with_context(db_session, organization_a)
    token_b, _organization_b = _login(client, "b@example.com", "pass-b")

    response = client.get(
        f"/api/v1/ai-search/summary?campaign_id={campaign.id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert response.status_code == 404
