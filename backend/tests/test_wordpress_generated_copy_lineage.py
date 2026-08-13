from __future__ import annotations

import json
from datetime import UTC, datetime

from app.enums import StrategyRecommendationStatus
from app.intelligence.contracts.governed_ai import GovernedActionDraft
from app.intelligence.executors.mutation_schema import build_mutation
from app.models.governed_ai import GovernedAIRun
from app.models.intelligence import StrategyRecommendation
from app.models.recommendation_execution import RecommendationExecution
from app.services import governed_ai_service
from app.services.governed_ai_draft_service import _output_payload
from app.services.wordpress_managed_content_validation_service import (
    validate_managed_wordpress_changes,
)
from app.utils.enum_guard import ensure_enum
from tests.conftest import create_test_campaign


ACTION_ID = "organic.rewrite_search_snippet"
TITLE = "Reno Junk Removal Services"
DESCRIPTION = (
    "See local junk removal services and choose the help that fits your cleanup."
)


def _managed_execution_with_ai_run(
    db_session,
    create_test_tenant,
    create_test_org,
) -> tuple[RecommendationExecution, GovernedAIRun, list[dict]]:
    tenant = create_test_tenant(name="Generated Copy Tenant")
    organization = create_test_org(
        tenant_id=tenant.id,
        name="Generated Copy Organization",
    )
    campaign = create_test_campaign(
        db_session,
        organization.id,
        tenant_id=tenant.id,
        name="Reno Junk Removal",
        domain="reno-junk.example",
    )
    recommendation = StrategyRecommendation(
        tenant_id=tenant.id,
        campaign_id=campaign.id,
        recommendation_type="fix_missing_title",
        rationale="Make the search result clearer for local customers.",
        confidence=0.9,
        confidence_score=0.9,
        evidence_json=json.dumps({"action_id": ACTION_ID, "target_url": "/"}),
        rollback_plan_json="{}",
        risk_tier=1,
        status=ensure_enum(
            StrategyRecommendationStatus.APPROVED,
            StrategyRecommendationStatus,
        ),
    )
    db_session.add(recommendation)
    db_session.flush()

    campaign_evidence_id = f"campaign:{campaign.id}"
    recommendation_evidence_id = f"recommendation:{recommendation.id}"
    input_snapshot = {
        "contract": {"ai_role": "draft_copy_for_saved_action_only"},
        "facts": {
            "campaign": {
                "evidence_id": campaign_evidence_id,
                "name": campaign.name,
                "domain": campaign.domain,
            },
            "recommendations": [
                {
                    "evidence_id": recommendation_evidence_id,
                    "rationale": recommendation.rationale,
                    "action_plan": {
                        "action_id": ACTION_ID,
                        "display_name": "Make the search result clearer",
                    },
                }
            ],
        },
        "allowed_actions": [{"action_id": ACTION_ID}],
        "allowed_evidence_ids": [campaign_evidence_id, recommendation_evidence_id],
        "draft_request": {
            "action_id": ACTION_ID,
            "draft_type": "search_result",
            "approval_required": True,
        },
        "required_output": {"approval_required": True},
    }
    output = GovernedActionDraft(
        action_id=ACTION_ID,
        draft_type="search_result",
        draft_state="ready",
        title=TITLE,
        body=DESCRIPTION,
        evidence_used=[campaign_evidence_id, recommendation_evidence_id],
        uncertainties=[],
        approval_required=True,
    )
    ai_run = GovernedAIRun(
        tenant_id=tenant.id,
        organization_id=organization.id,
        campaign_id=campaign.id,
        feature="intelligence_draft",
        provider_name="mistral",
        model_name="mistral-small",
        prompt_template_version="insightos-governed-action-draft-v1",
        lexicon_id="insightos-seo-lexicon",
        lexicon_version="1.0.0",
        context_hash=governed_ai_service._hash_payload(input_snapshot),
        prompt_hash="a" * 64,
        response_hash="b" * 64,
        idempotency_key=f"ai:wordpress-lineage:{recommendation.id}",
        status="validated",
        provider_state="ready",
        selected_action_id=ACTION_ID,
        allowed_action_ids=[ACTION_ID],
        evidence_refs=[campaign_evidence_id, recommendation_evidence_id],
        output_payload=_output_payload(output, context=input_snapshot),
        completed_at=datetime.now(UTC),
    )
    db_session.add(ai_run)
    db_session.flush()

    execution = RecommendationExecution(
        recommendation_id=recommendation.id,
        campaign_id=campaign.id,
        execution_type="fix_missing_title",
        execution_payload=json.dumps(
            {
                "tenant_id": tenant.id,
                "organization_id": organization.id,
                "managed_wordpress_automation": True,
                "automation_policy_version": 4,
                "content_generation_mode": "governed_ai",
                "governed_ai_run_id": ai_run.id,
                "recommendation_context": {"action_id": ACTION_ID},
            },
            sort_keys=True,
        ),
        idempotency_key=f"wordpress-lineage:{recommendation.id}",
        deterministic_hash="c" * 64,
        status="scheduled",
    )
    db_session.add(execution)
    db_session.commit()
    mutations = [
        build_mutation(
            action="update_meta_title",
            target_url="/",
            payload={"title": TITLE},
        ),
        build_mutation(
            action="update_meta_description",
            target_url="/",
            payload={"description": DESCRIPTION},
        ),
    ]
    return execution, ai_run, mutations


def test_generated_wordpress_copy_keeps_complete_replayable_lineage(
    db_session,
    create_test_tenant,
    create_test_org,
) -> None:
    execution, ai_run, mutations = _managed_execution_with_ai_run(
        db_session,
        create_test_tenant,
        create_test_org,
    )

    report = validate_managed_wordpress_changes(
        db_session,
        execution=execution,
        mutations=mutations,
    )

    assert report["status"] == "passed"
    assert report["validator_version"] == "wordpress-managed-content-v2"
    assert report["traceability"]["generation_mode"] == "governed_ai"
    lineage = report["traceability"]["generated_copy_lineage"]
    assert lineage["run_id"] == ai_run.id
    assert lineage["model_name"] == "mistral-small"
    assert lineage["prompt_template_version"] == "insightos-governed-action-draft-v1"
    assert lineage["lexicon_version"] == "1.0.0"
    assert lineage["context_hash"] == ai_run.context_hash
    assert lineage["input_snapshot"]["facts"]["campaign"]["name"] == (
        "Reno Junk Removal"
    )
    assert lineage["evidence_used"] == ai_run.output_payload["evidence_used"]


def test_generated_wordpress_copy_fails_closed_when_wording_or_lineage_changes(
    db_session,
    create_test_tenant,
    create_test_org,
) -> None:
    execution, ai_run, mutations = _managed_execution_with_ai_run(
        db_session,
        create_test_tenant,
        create_test_org,
    )
    mutations[1]["payload"]["description"] = "Different wording"

    mismatch = validate_managed_wordpress_changes(
        db_session,
        execution=execution,
        mutations=mutations,
    )

    assert mismatch["status"] == "blocked"
    assert {
        issue["code"] for issue in mismatch["blocking_issues"]
    } >= {"wordpress_generated_copy_mismatch"}

    mutations[1]["payload"]["description"] = DESCRIPTION
    ai_run.response_hash = None
    db_session.commit()
    incomplete = validate_managed_wordpress_changes(
        db_session,
        execution=execution,
        mutations=mutations,
    )

    assert incomplete["status"] == "blocked"
    assert {
        issue["code"] for issue in incomplete["blocking_issues"]
    } >= {"wordpress_generated_copy_lineage_incomplete"}


def test_generated_wordpress_copy_requires_a_saved_ai_run(
    db_session,
    create_test_tenant,
    create_test_org,
) -> None:
    execution, _, mutations = _managed_execution_with_ai_run(
        db_session,
        create_test_tenant,
        create_test_org,
    )
    payload = json.loads(execution.execution_payload)
    payload.pop("governed_ai_run_id")
    execution.execution_payload = json.dumps(payload, sort_keys=True)
    db_session.commit()

    report = validate_managed_wordpress_changes(
        db_session,
        execution=execution,
        mutations=mutations,
    )

    assert report["status"] == "blocked"
    assert {
        issue["code"] for issue in report["blocking_issues"]
    } >= {"wordpress_generated_copy_run_required"}
