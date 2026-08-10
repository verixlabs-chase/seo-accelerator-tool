from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json

from fastapi import HTTPException
import pytest

from app.models.audit_log import AuditLog
from app.models.provider_metric_contract import ProviderMetricContractVersion
from app.models.reference_library import StandardsChangeCandidate, StandardsSourceSnapshot
from app.reference_library.paths import reference_library_file
from app.services import (
    metric_contract_service,
    reference_library_service,
    standards_replay_service,
    standards_rollout_service,
    standards_source_service,
)


def _login(client, email: str, password: str) -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def _reviewed_change(db_session, *, source_id: str = "google.search_console.metrics"):
    sources = standards_source_service.ensure_default_sources(db_session)
    source = next(row for row in sources if row.source_id == source_id)
    previous = StandardsSourceSnapshot(
        source_id=source_id,
        source_uri=source.source_uri,
        source_format=source.source_format,
        parser_version=source.parser_version,
        http_status=200,
        source_digest="1" * 64,
        normalized_digest="2" * 64,
        content_bytes=18,
        content_text="Clicks count a visit.",
        observed_at=datetime(2026, 8, 8, tzinfo=UTC),
    )
    current = StandardsSourceSnapshot(
        source_id=source_id,
        source_uri=source.source_uri,
        source_format=source.source_format,
        parser_version=source.parser_version,
        http_status=200,
        source_digest="3" * 64,
        normalized_digest="4" * 64,
        content_bytes=32,
        content_text="Clicks use a changed definition.",
        observed_at=datetime(2026, 8, 9, tzinfo=UTC),
    )
    db_session.add_all([previous, current])
    db_session.flush()
    change = StandardsChangeCandidate(
        source_id=source_id,
        previous_snapshot_id=previous.id,
        current_snapshot_id=current.id,
        classification_version="i1.6b.v1",
        change_type="metric_definition_change",
        materiality="material",
        status="requires_contract_update",
        title="Published measurement definition changed",
        summary="A reviewed definition change requires a candidate contract.",
        diff_json="{}",
        classification_reasons_json="[]",
        automatic_activation_allowed=False,
        review_disposition="requires_contract_update",
        reviewed_by_user_id="platform-reviewer",
        reviewed_at=datetime(2026, 8, 9, tzinfo=UTC),
    )
    db_session.add(change)
    db_session.commit()
    return change


def _candidate_replay(db_session, *, contract_id: str = "search_console.clicks"):
    change = _reviewed_change(db_session)
    proposed = standards_replay_service.create_metric_contract_candidate(
        db_session,
        standards_change_candidate_id=change.id,
        contract_id=contract_id,
        candidate_version="2.0",
        changes={"unit": "qualified_clicks", "definition": "Verified qualified clicks."},
        actor_user_id="platform-owner",
    )
    replay = standards_replay_service.replay_metric_contract_candidate(
        db_session,
        candidate_contract_version_id=proposed["candidate"]["id"],
        actor_user_id="platform-owner",
        sample_type="combined",
        evidence_samples=[
            {
                "before_value": 100,
                "after_value": 120,
                "before_scope_key": "before",
                "after_scope_key": "after",
            }
        ],
        approval_reference="owner-reviewed-evidence",
    )
    return change, proposed, replay


def _approval_body() -> dict:
    return {
        "decision": "approved",
        "rationale": "The replay is understood and the comparison boundary is accepted.",
        "rollout_plan": {
            "summary": "Activate the reviewed contract and watch collection health.",
            "steps": ["Activate the candidate", "Check provider collection"],
            "monitoring_window_hours": 24,
        },
        "rollback_plan": {
            "summary": "Restore the prior contract if collection changes unexpectedly.",
            "steps": ["Restore the prior version", "Run the replay again"],
            "monitoring_window_hours": 24,
        },
        "acknowledges_new_baseline": True,
    }


def _reference_artifacts() -> dict:
    return {
        "metrics": json.loads(
            reference_library_file("metrics", "core_web_vitals.json").read_text(
                encoding="utf-8"
            )
        ),
        "recommendations": json.loads(
            reference_library_file("recommendations", "perf_recommendations.json").read_text(
                encoding="utf-8"
            )
        ),
        "intelligence_lexicon": json.loads(
            reference_library_file("intelligence", "seo_intelligence_v1.json").read_text(
                encoding="utf-8"
            )
        ),
    }


def test_only_platform_owner_can_approve_execute_and_rollback(client, db_session) -> None:
    change, proposed, replay = _candidate_replay(db_session)
    admin_token = _login(client, "platform-admin@example.com", "pass-platform-admin")
    owner_token = _login(client, "platform-owner@example.com", "pass-platform-owner")
    tenant_token = _login(client, "a@example.com", "pass-a")

    status_for_tenant = client.get(
        "/api/v1/reference-library/standards/status",
        headers={"Authorization": f"Bearer {tenant_token}"},
    )
    assert status_for_tenant.status_code == 403

    blocked = client.post(
        f"/api/v1/reference-library/standards/replays/{replay['id']}/decision",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=_approval_body(),
    )
    assert blocked.status_code == 403

    approved = client.post(
        f"/api/v1/reference-library/standards/replays/{replay['id']}/decision",
        headers={"Authorization": f"Bearer {owner_token}"},
        json=_approval_body(),
    )
    assert approved.status_code == 200
    approval_id = approved.json()["data"]["id"]
    assert approved.json()["data"]["automatic_activation_allowed"] is False

    activated = client.post(
        f"/api/v1/reference-library/standards/approvals/{approval_id}/rollouts",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"rollout_mode": "immediate"},
    )
    assert activated.status_code == 200, activated.text
    rollout = activated.json()["data"]
    assert rollout["status"] == "completed"

    candidate = db_session.get(ProviderMetricContractVersion, proposed["candidate"]["id"])
    base = db_session.get(ProviderMetricContractVersion, proposed["base"]["id"])
    db_session.refresh(candidate)
    db_session.refresh(base)
    assert candidate.is_active is True
    assert base.is_active is False
    assert metric_contract_service.contract_definition(
        "search_console.clicks", db=db_session
    ).version == "2.0"
    db_session.refresh(change)
    assert change.status == "implemented"

    rolled_back = client.post(
        f"/api/v1/reference-library/standards/rollouts/{rollout['id']}/rollback",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"reason": "The monitoring window showed an unexpected collection change."},
    )
    assert rolled_back.status_code == 200, rolled_back.text
    assert rolled_back.json()["data"]["status"] == "rolled_back"
    assert metric_contract_service.contract_definition(
        "search_console.clicks", db=db_session
    ).version == "1.0"
    db_session.refresh(change)
    assert change.status == "requires_contract_update"

    events = {
        row.event_type
        for row in db_session.query(AuditLog).filter(AuditLog.event_type.like("standards.%"))
    }
    assert {
        "standards.replay.approved",
        "standards.rollout.scheduled",
        "standards.rollout.completed",
        "standards.rollout.rolled_back",
    }.issubset(events)


def test_scheduled_rollout_waits_and_approval_seal_blocks_changed_candidate(
    client, db_session
) -> None:
    _change, proposed, replay = _candidate_replay(
        db_session, contract_id="search_console.impressions"
    )
    owner_token = _login(client, "platform-owner@example.com", "pass-platform-owner")
    approved = client.post(
        f"/api/v1/reference-library/standards/replays/{replay['id']}/decision",
        headers={"Authorization": f"Bearer {owner_token}"},
        json=_approval_body(),
    )
    assert approved.status_code == 200
    approval_id = approved.json()["data"]["id"]
    scheduled_for = datetime.now(UTC) + timedelta(hours=2)
    scheduled = client.post(
        f"/api/v1/reference-library/standards/approvals/{approval_id}/rollouts",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"rollout_mode": "scheduled", "scheduled_for": scheduled_for.isoformat()},
    )
    assert scheduled.status_code == 200
    rollout_id = scheduled.json()["data"]["id"]

    too_early = client.post(
        f"/api/v1/reference-library/standards/rollouts/{rollout_id}/execute",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert too_early.status_code == 409

    candidate = db_session.get(ProviderMetricContractVersion, proposed["candidate"]["id"])
    candidate.content_hash = "f" * 64
    db_session.commit()
    candidate.lifecycle_status = "candidate"
    candidate.is_active = False
    db_session.commit()

    with pytest.raises(standards_rollout_service.StandardsRolloutError, match="changed"):
        standards_rollout_service.execute_rollout(
            db_session,
            rollout_id=rollout_id,
            actor_user_id="platform-owner",
            audit_tenant_id="tenant-a",
            now=scheduled_for + timedelta(minutes=1),
        )

    status = client.get(
        "/api/v1/reference-library/standards/status",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert status.status_code == 200
    payload = status.json()["data"]
    assert payload["automatic_activation_allowed"] is False
    assert payload["summary"]["scheduled_rollouts"] == 1


def test_lexicon_replacement_requires_approved_rollout_and_can_rollback(db_session) -> None:
    tenant_id = "standards-lexicon-tenant"
    actor = "platform-owner"
    base_artifacts = _reference_artifacts()
    validated = reference_library_service.validate_version(
        db_session,
        tenant_id=tenant_id,
        actor_user_id=actor,
        version="1.0.0",
        artifacts=base_artifacts,
        strict_mode=True,
    )
    assert validated["status"] == "passed"
    reference_library_service.activate_version(
        db_session,
        tenant_id=tenant_id,
        actor_user_id=actor,
        version="1.0.0",
        reason="Initial bootstrap",
    )

    candidate_artifacts = deepcopy(base_artifacts)
    lexicon = candidate_artifacts["intelligence_lexicon"]
    lexicon["meta"]["version"] = "1.1.0"
    lcp = next(item for item in lexicon["metrics"] if item["metric_id"] == "cwv.lcp")
    lcp["thresholds"]["good_boundary"] = 2400
    candidate_validation = reference_library_service.validate_version(
        db_session,
        tenant_id=tenant_id,
        actor_user_id=actor,
        version="1.1.0",
        artifacts=candidate_artifacts,
        strict_mode=True,
    )
    assert candidate_validation["status"] == "passed"

    with pytest.raises(HTTPException, match="sealed replay"):
        reference_library_service.activate_version(
            db_session,
            tenant_id=tenant_id,
            actor_user_id=actor,
            version="1.1.0",
            reason="Must be blocked",
        )

    replay = standards_replay_service.replay_lexicon_candidate(
        db_session,
        tenant_id=tenant_id,
        candidate_version="1.1.0",
        actor_user_id=actor,
    )
    approval = standards_rollout_service.decide_replay_report(
        db_session,
        replay_report_id=replay["id"],
        decision="approved",
        rationale="The governed threshold replay is understood.",
        rollout_plan=_approval_body()["rollout_plan"],
        rollback_plan=_approval_body()["rollback_plan"],
        acknowledges_new_baseline=False,
        actor_user_id=actor,
        audit_tenant_id=tenant_id,
    )
    rollout = standards_rollout_service.create_rollout(
        db_session,
        approval_id=approval["id"],
        rollout_mode="immediate",
        scheduled_for=None,
        actor_user_id=actor,
        audit_tenant_id=tenant_id,
    )
    completed = standards_rollout_service.execute_rollout(
        db_session,
        rollout_id=rollout["id"],
        actor_user_id=actor,
        audit_tenant_id=tenant_id,
    )
    assert completed["status"] == "completed"
    assert reference_library_service.get_active(db_session, tenant_id)["version"] == "1.1.0"

    restored = standards_rollout_service.rollback_rollout(
        db_session,
        rollout_id=rollout["id"],
        reason="Restore the prior governed threshold.",
        actor_user_id=actor,
        audit_tenant_id=tenant_id,
    )
    assert restored["status"] == "rolled_back"
    assert reference_library_service.get_active(db_session, tenant_id)["version"] == "1.0.0"
