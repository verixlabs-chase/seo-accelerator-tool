import pytest
from fastapi import HTTPException

from app.models.campaign import Campaign
from app.models.tenant import Tenant
from app.schemas.intelligence import IntelligenceScoreOut, RecommendationOut
from app.services import intelligence_service


def test_intelligence_score_recommendations_and_advance_month(db_session):
    tenant = db_session.query(Tenant).filter(Tenant.name == "Tenant A").first()
    assert tenant is not None

    campaign = Campaign(
        tenant_id=tenant.id,
        organization_id=tenant.id,
        name="Intelligence Campaign",
        domain="intel.com",
    )
    db_session.add(campaign)
    db_session.commit()
    db_session.refresh(campaign)

    score = intelligence_service.get_latest_score(db_session, tenant_id=tenant.id, campaign_id=campaign.id)
    score_payload = IntelligenceScoreOut.model_validate(score).model_dump(mode="json")
    assert "score_value" in score_payload

    recs = intelligence_service.get_recommendations(db_session, tenant_id=tenant.id, campaign_id=campaign.id)
    items = [RecommendationOut.model_validate(row).model_dump(mode="json") for row in recs]
    assert len(items) >= 1
    first = items[0]
    assert "confidence_score" in first
    assert isinstance(first["confidence_score"], float)
    assert 0.0 <= first["confidence_score"] <= 1.0
    assert "evidence" in first
    assert isinstance(first["evidence"], list)
    assert len(first["evidence"]) >= 1
    assert "risk_tier" in first
    assert isinstance(first["risk_tier"], int)
    assert 0 <= first["risk_tier"] <= 4
    assert "rollback_plan" in first
    assert isinstance(first["rollback_plan"], dict)
    assert len(first["rollback_plan"]) >= 1

    with pytest.raises(HTTPException) as invalid_transition:
        intelligence_service.transition_recommendation_state(
            db_session,
            tenant_id=tenant.id,
            campaign_id=campaign.id,
            recommendation_id=first["id"],
            target_state="APPROVED",
        )
    assert invalid_transition.value.status_code == 400

    validated = intelligence_service.transition_recommendation_state(
        db_session,
        tenant_id=tenant.id,
        campaign_id=campaign.id,
        recommendation_id=first["id"],
        target_state="VALIDATED",
    )
    assert validated.status == "VALIDATED"

    approved = intelligence_service.transition_recommendation_state(
        db_session,
        tenant_id=tenant.id,
        campaign_id=campaign.id,
        recommendation_id=first["id"],
        target_state="APPROVED",
    )
    assert approved.status == "APPROVED"

    with pytest.raises(HTTPException) as blocked:
        intelligence_service.advance_month(
            db_session,
            tenant_id=tenant.id,
            campaign_id=campaign.id,
            override=False,
        )
    assert blocked.value.status_code == 400

    advanced = intelligence_service.advance_month(
        db_session,
        tenant_id=tenant.id,
        campaign_id=campaign.id,
        override=True,
    )
    assert advanced["advanced_to_month"] == 2
