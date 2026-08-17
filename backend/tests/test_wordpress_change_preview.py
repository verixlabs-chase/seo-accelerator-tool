from __future__ import annotations

import json

import pytest

from app.enums import StrategyRecommendationStatus
from app.intelligence.recommendation_execution_engine import (
    approve_execution,
    execute_recommendation,
    schedule_execution,
)
from app.models.execution_mutation import ExecutionMutation
from app.models.intelligence import StrategyRecommendation
from app.models.recommendation_execution import RecommendationExecution
from app.models.wordpress_change_preview import WordPressChangePreview
from app.services.wordpress_change_preview_service import WordPressChangePreviewError
from app.utils.enum_guard import ensure_enum
from tests.conftest import create_test_campaign


def _execution(db_session, create_test_tenant, create_test_org) -> RecommendationExecution:
    tenant = create_test_tenant(name="Preview Tenant")
    organization = create_test_org(tenant_id=tenant.id, name="Preview Organization")
    organization.plan_type = "multi_location"
    db_session.commit()
    campaign = create_test_campaign(
        db_session,
        organization.id,
        tenant_id=tenant.id,
        name="Preview Campaign",
        domain="preview.example",
    )
    recommendation = StrategyRecommendation(
        tenant_id=tenant.id,
        campaign_id=campaign.id,
        recommendation_type="fix_missing_title",
        rationale="Make the page clearer in search results.",
        confidence=0.9,
        confidence_score=0.9,
        evidence_json=json.dumps(
            {
                "target_url": "/services",
                "meta_title": "Trusted Local Service | Preview Campaign",
                "meta_description": "See the services available from Preview Campaign.",
            }
        ),
        rollback_plan_json="{}",
        status=ensure_enum(StrategyRecommendationStatus.APPROVED, StrategyRecommendationStatus),
    )
    db_session.add(recommendation)
    db_session.commit()
    execution = schedule_execution(recommendation.id, db=db_session)
    assert isinstance(execution, RecommendationExecution)
    return execution


def test_wordpress_preview_is_durable_and_contains_exact_change_contract(
    db_session,
    create_test_tenant,
    create_test_org,
) -> None:
    execution = _execution(db_session, create_test_tenant, create_test_org)

    planned = execute_recommendation(execution.id, db=db_session, dry_run=True)

    assert isinstance(planned, dict)
    preview = planned["preview"]
    assert preview["status"] == "ready"
    assert preview["mutation_count"] == 2
    assert preview["conflict_count"] == 0
    assert preview["affected_urls"] == ["/services"]
    assert preview["managed_content_validation"]["status"] == "not_required"
    assert all(item["expected_version"]["revision_id"] for item in preview["changes"])
    assert all(len(item["expected_version"]["content_hash"]) == 64 for item in preview["changes"])
    assert all(item["rollback_plan"]["available"] for item in preview["changes"])
    row = db_session.query(WordPressChangePreview).filter_by(execution_id=execution.id).one()
    assert row.preview_hash == preview["preview_hash"]
    assert row.status == "ready"


def test_wordpress_approval_requires_the_exact_ready_preview(
    db_session,
    create_test_tenant,
    create_test_org,
) -> None:
    execution = _execution(db_session, create_test_tenant, create_test_org)

    with pytest.raises(WordPressChangePreviewError) as missing:
        approve_execution(execution.id, approved_by="owner", db=db_session)
    assert missing.value.reason_code == "wordpress_preview_required"

    planned = execute_recommendation(execution.id, db=db_session, dry_run=True)
    assert isinstance(planned, dict)
    preview_hash = planned["preview"]["preview_hash"]
    approved = approve_execution(
        execution.id,
        approved_by="owner",
        preview_hash=preview_hash,
        db=db_session,
    )

    assert approved is not None
    assert approved.approved_by == "owner"
    preview_row = db_session.query(WordPressChangePreview).filter_by(execution_id=execution.id).one()
    assert preview_row.status == "approved"
    assert preview_row.approved_by == "owner"


def test_live_wordpress_mutations_are_bound_to_the_approved_page_version(
    db_session,
    create_test_tenant,
    create_test_org,
) -> None:
    execution = _execution(db_session, create_test_tenant, create_test_org)
    planned = execute_recommendation(execution.id, db=db_session, dry_run=True)
    assert isinstance(planned, dict)
    approve_execution(
        execution.id,
        approved_by="owner",
        preview_hash=planned["preview"]["preview_hash"],
        db=db_session,
    )

    completed = execute_recommendation(execution.id, db=db_session)

    assert isinstance(completed, RecommendationExecution)
    assert completed.status == "completed"
    rows = db_session.query(ExecutionMutation).filter_by(execution_id=execution.id).all()
    assert len(rows) == 2
    for row in rows:
        mutation = json.loads(row.mutation_payload)
        assert mutation["expected_version"]["revision_id"]
        assert len(mutation["expected_version"]["content_hash"]) == 64


def test_change_preview_api_rejects_approval_without_preview_hash(
    client,
    db_session,
    create_test_org,
) -> None:
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "org-admin@example.com", "password": "pass-org-admin"},
    )
    token = login.json()["data"]["access_token"]
    from app.models.user import User

    user = db_session.query(User).filter(User.email == "org-admin@example.com").one()
    organization = create_test_org(tenant_id=user.tenant_id, name="Preview API Organization")
    organization.plan_type = "multi_location"
    db_session.commit()
    campaign = create_test_campaign(
        db_session,
        organization.id,
        tenant_id=user.tenant_id,
        name="Preview API Campaign",
        domain="preview-api.example",
    )
    recommendation = StrategyRecommendation(
        tenant_id=user.tenant_id,
        campaign_id=campaign.id,
        recommendation_type="fix_missing_title",
        rationale="Preview API",
        confidence=0.9,
        confidence_score=0.9,
        evidence_json="{}",
        rollback_plan_json="{}",
        status=ensure_enum(StrategyRecommendationStatus.APPROVED, StrategyRecommendationStatus),
    )
    db_session.add(recommendation)
    db_session.commit()
    execution = schedule_execution(recommendation.id, db=db_session)
    assert isinstance(execution, RecommendationExecution)

    response = client.post(
        f"/api/v1/executions/{execution.id}/approve",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 409
    assert response.json()["errors"][0]["details"]["reason_code"] == "wordpress_preview_required"
