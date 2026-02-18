import json

import pytest
from fastapi import HTTPException

from app.models.campaign import Campaign
from app.models.intelligence import StrategyRecommendation
from app.models.tenant import Tenant
from app.services.intelligence_service import transition_recommendation_state


@pytest.mark.parametrize(
    ("from_state", "to_state", "should_pass"),
    [
        ("DRAFT", "GENERATED", True),
        ("GENERATED", "VALIDATED", True),
        ("GENERATED", "APPROVED", False),
        ("VALIDATED", "APPROVED", True),
        ("APPROVED", "SCHEDULED", True),
        ("SCHEDULED", "EXECUTED", True),
        ("EXECUTED", "ROLLED_BACK", True),
        ("ROLLED_BACK", "ARCHIVED", True),
        ("ARCHIVED", "GENERATED", False),
    ],
)
def test_recommendation_state_guards(db_session, from_state, to_state, should_pass):
    tenant = db_session.query(Tenant).filter(Tenant.name == "Tenant A").first()
    assert tenant is not None
    campaign = Campaign(tenant_id=tenant.id, name="Lifecycle Guard Campaign", domain="guards.com")
    db_session.add(campaign)
    db_session.flush()

    rec = StrategyRecommendation(
        tenant_id=tenant.id,
        campaign_id=campaign.id,
        recommendation_type="test_transition",
        rationale="state guard test",
        confidence=0.8,
        confidence_score=0.8,
        evidence_json=json.dumps(["fixture_evidence"]),
        risk_tier=1,
        rollback_plan_json=json.dumps({"steps": ["undo_change"]}),
        status=from_state,
    )
    db_session.add(rec)
    db_session.commit()

    if should_pass:
        transitioned = transition_recommendation_state(
            db_session,
            tenant_id=tenant.id,
            campaign_id=campaign.id,
            recommendation_id=rec.id,
            target_state=to_state,
        )
        assert transitioned.status == to_state
    else:
        with pytest.raises(HTTPException):
            transition_recommendation_state(
                db_session,
                tenant_id=tenant.id,
                campaign_id=campaign.id,
                recommendation_id=rec.id,
                target_state=to_state,
            )
