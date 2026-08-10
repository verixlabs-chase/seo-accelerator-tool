from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import json

import pytest

from app.models.provider_metric_contract import ProviderMetricContractVersion
from app.models.reference_library import (
    StandardsChangeCandidate,
    StandardsImpactLink,
    StandardsSourceSnapshot,
)
from app.models.standards_replay import StandardsReplayReport
from app.reference_library.paths import reference_library_file
from app.services import (
    metric_contract_service,
    reference_library_service,
    standards_replay_service,
    standards_source_service,
)


def _login(client, email: str, password: str) -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def _reviewed_change(db_session) -> StandardsChangeCandidate:
    standards_source_service.ensure_default_sources(db_session)
    source_id = "google.search_console.metrics"
    source = next(
        row
        for row in standards_source_service.ensure_default_sources(db_session)
        if row.source_id == source_id
    )
    previous = StandardsSourceSnapshot(
        source_id=source_id,
        source_uri=source.source_uri,
        source_format="html",
        parser_version=source.parser_version,
        http_status=200,
        source_digest="1" * 64,
        normalized_digest="2" * 64,
        content_bytes=20,
        content_text="Clicks are counted per visit.",
        observed_at=datetime(2026, 8, 8, tzinfo=UTC),
    )
    current = StandardsSourceSnapshot(
        source_id=source_id,
        source_uri=source.source_uri,
        source_format="html",
        parser_version=source.parser_version,
        http_status=200,
        source_digest="3" * 64,
        normalized_digest="4" * 64,
        content_bytes=30,
        content_text="Clicks now use a changed metric definition.",
        observed_at=datetime(2026, 8, 9, tzinfo=UTC),
    )
    db_session.add_all([previous, current])
    db_session.flush()
    candidate = StandardsChangeCandidate(
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
    db_session.add(candidate)
    db_session.flush()
    db_session.add_all(
        [
            StandardsImpactLink(
                candidate_id=candidate.id,
                impact_type="action_contract",
                impact_key="search_visibility_actions",
                impact_reason="Search actions use the changed metric.",
                risk_state="fail_closed",
                is_blocking=True,
            ),
            StandardsImpactLink(
                candidate_id=candidate.id,
                impact_type="historical_comparison",
                impact_key="search_console_performance",
                impact_reason="Definition changes may invalidate comparisons.",
                risk_state="review_required",
                is_blocking=False,
            ),
        ]
    )
    db_session.commit()
    return candidate


def _reference_artifacts() -> dict:
    return {
        "metrics": json.loads(
            reference_library_file("metrics", "core_web_vitals.json").read_text(encoding="utf-8")
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


def test_metric_candidate_is_inactive_and_replay_marks_version_boundary(db_session) -> None:
    change = _reviewed_change(db_session)
    metric_contract_service.ensure_default_contracts(db_session)

    proposed = standards_replay_service.create_metric_contract_candidate(
        db_session,
        standards_change_candidate_id=change.id,
        contract_id="search_console.clicks",
        candidate_version="2.0",
        changes={"unit": "qualified_clicks", "definition": "Verified qualified clicks."},
        actor_user_id="platform-owner",
    )

    candidate = db_session.get(
        ProviderMetricContractVersion,
        proposed["candidate"]["id"],
    )
    assert candidate is not None
    assert candidate.is_active is False
    assert candidate.lifecycle_status == "candidate"
    assert candidate.supersedes_version_id == proposed["base"]["id"]
    assert proposed["comparison_boundary"]["required"] is True
    assert proposed["automatic_activation_allowed"] is False

    report = standards_replay_service.replay_metric_contract_candidate(
        db_session,
        candidate_contract_version_id=candidate.id,
        actor_user_id="platform-owner",
        sample_type="combined",
        evidence_samples=[
            {
                "before_value": 100,
                "after_value": 120,
                "before_scope_key": "same",
                "after_scope_key": "same",
            }
        ],
        approval_reference="security-review-2026-08-09",
    )

    assert report["status"] == "changed"
    assert report["requires_new_baseline"] is True
    assert report["invalidated_comparisons"] >= 1
    assert report["changed_actions"] == 1
    assert report["automatic_activation_allowed"] is False
    stored = db_session.get(StandardsReplayReport, report["id"])
    assert stored is not None
    assert stored.approval_reference_digest
    assert "security-review" not in stored.replay_results_json


def test_approved_evidence_requires_approval_and_rejects_identity_fields(db_session) -> None:
    change = _reviewed_change(db_session)
    proposed = standards_replay_service.create_metric_contract_candidate(
        db_session,
        standards_change_candidate_id=change.id,
        contract_id="search_console.impressions",
        candidate_version="2.0",
        changes={"definition": "A reviewed impressions definition."},
        actor_user_id="platform-owner",
    )

    with pytest.raises(standards_replay_service.StandardsReplayError):
        standards_replay_service.replay_metric_contract_candidate(
            db_session,
            candidate_contract_version_id=proposed["candidate"]["id"],
            actor_user_id="platform-owner",
            sample_type="approved_evidence",
            evidence_samples=[{"before_value": 1, "after_value": 2}],
        )
    with pytest.raises(standards_replay_service.StandardsReplayError):
        standards_replay_service.replay_metric_contract_candidate(
            db_session,
            candidate_contract_version_id=proposed["candidate"]["id"],
            actor_user_id="platform-owner",
            sample_type="approved_evidence",
            evidence_samples=[
                {"before_value": 1, "after_value": 2, "tenant_id": "must-not-be-accepted"}
            ],
            approval_reference="approved",
        )


def test_lexicon_replay_reports_threshold_changes_without_false_baseline_reset(db_session) -> None:
    tenant_id = "tenant-a"
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
        reason="replay base",
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

    report = standards_replay_service.replay_lexicon_candidate(
        db_session,
        tenant_id=tenant_id,
        candidate_version="1.1.0",
        actor_user_id=actor,
    )

    assert report["artifact_type"] == "intelligence_lexicon"
    assert report["changed_results"] > 0
    assert report["requires_new_baseline"] is False
    assert report["definition_diff"]["metrics"][0]["key"] == "cwv.lcp"
    assert report["automatic_activation_allowed"] is False


def test_replay_endpoints_are_platform_only(client, db_session) -> None:
    change = _reviewed_change(db_session)
    tenant_token = _login(client, "a@example.com", "pass-a")
    forbidden = client.post(
        "/api/v1/reference-library/standards/contracts/candidates",
        headers={"Authorization": f"Bearer {tenant_token}"},
        json={
            "standards_change_candidate_id": change.id,
            "contract_id": "search_console.clicks",
            "candidate_version": "2.0",
            "changes": {"definition": "Changed click definition."},
        },
    )
    assert forbidden.status_code == 403

    platform_token = _login(client, "platform-admin@example.com", "pass-platform-admin")
    proposed = client.post(
        "/api/v1/reference-library/standards/contracts/candidates",
        headers={"Authorization": f"Bearer {platform_token}"},
        json={
            "standards_change_candidate_id": change.id,
            "contract_id": "search_console.clicks",
            "candidate_version": "2.0",
            "changes": {"definition": "Changed click definition."},
        },
    )
    assert proposed.status_code == 200
    candidate_id = proposed.json()["data"]["candidate"]["id"]

    versions = client.get(
        "/api/v1/reference-library/standards/contracts/versions"
        "?contract_id=search_console.clicks&lifecycle_status=candidate",
        headers={"Authorization": f"Bearer {platform_token}"},
    )
    assert versions.status_code == 200
    assert versions.json()["data"]["items"][0]["id"] == candidate_id

    replayed = client.post(
        f"/api/v1/reference-library/standards/contracts/candidates/{candidate_id}/replay",
        headers={"Authorization": f"Bearer {platform_token}"},
        json={"sample_type": "fixed_fixture"},
    )
    assert replayed.status_code == 200
    report_id = replayed.json()["data"]["id"]
    detail = client.get(
        f"/api/v1/reference-library/standards/replays/{report_id}",
        headers={"Authorization": f"Bearer {platform_token}"},
    )
    assert detail.status_code == 200
    assert detail.json()["data"]["automatic_activation_allowed"] is False
