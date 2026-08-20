from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models.launch_readiness import LaunchReadinessDecision, LaunchReadinessProof
from app.models.provider_health import ProviderHealthState


def _login(client, email: str, password: str) -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def test_launch_readiness_keeps_runtime_facts_and_live_proof_separate(client, db_session) -> None:
    token = _login(client, "platform-owner@example.com", "pass-platform-owner")
    now = datetime.now(UTC)
    db_session.add(
        ProviderHealthState(
            tenant_id="launch-readiness-tenant",
            environment="production",
            provider_name="rank",
            provider_version="1.0.0",
            capability="rank_snapshot",
            breaker_state="closed",
            consecutive_failures=0,
            success_rate_1h=1.0,
            p95_latency_ms_1h=120,
            last_success_at=now,
            updated_at=now,
        )
    )
    db_session.commit()

    response = client.get(
        "/api/v1/system/launch-readiness",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["schema_version"] == "ops1-launch-readiness-v1"
    assert payload["overall_state"] == "no_go"
    assert payload["counts"]["blocker"] >= 1
    items = {item["code"]: item for item in payload["items"]}
    assert items["provider_health"]["state"] == "pass"
    assert items["critical_journeys"]["state"] == "needs_live_proof"
    assert items["first_use_comprehension"]["state"] == "needs_live_proof"
    assert items["billing_configuration"]["evidence"].endswith(
        "the billing provider was not contacted."
    )
    assert any("No weighted readiness score" in item for item in payload["limitations"])
    assert "stripe_secret_key" not in str(payload).lower()
    assert "provider_name" not in items["provider_health"]["facts"]


def test_launch_readiness_requires_platform_role(client) -> None:
    token = _login(client, "org-admin@example.com", "pass-org-admin")
    response = client.get(
        "/api/v1/system/launch-readiness",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_platform_owner_appends_idempotent_time_bounded_proof(client, db_session) -> None:
    token = _login(client, "platform-owner@example.com", "pass-platform-owner")
    now = datetime.now(UTC)
    body = {
        "gate_code": "critical_journeys",
        "result": "passed",
        "proof_kind": "production_smoke",
        "summary": "The current production Solo journey completed with the expected saved evidence.",
        "evidence_reference": "RELEASE-2026-08-20-04",
        "observed_at": (now - timedelta(minutes=1)).isoformat(),
        "expires_at": (now + timedelta(days=30)).isoformat(),
    }

    first = client.post(
        "/api/v1/system/launch-readiness/proofs",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert first.status_code == 200
    assert first.json()["data"]["created"] is True
    readiness = first.json()["data"]["readiness"]
    item = next(item for item in readiness["items"] if item["code"] == "critical_journeys")
    assert item["state"] == "needs_live_proof"
    assert item["facts"]["required_viewport_count"] == 38
    assert item["facts"]["missing_route_count"] == 19
    assert item["proof"]["evidence_reference"] == "RELEASE-2026-08-20-04"

    repeat = client.post(
        "/api/v1/system/launch-readiness/proofs",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert repeat.status_code == 200
    assert repeat.json()["data"]["created"] is False
    assert db_session.query(LaunchReadinessProof).count() == 1

    failed_body = {
        **body,
        "result": "failed",
        "summary": "The current production billing recovery journey did not restore active access.",
        "evidence_reference": "RELEASE-2026-08-20-05",
        "observed_at": now.isoformat(),
    }
    failed = client.post(
        "/api/v1/system/launch-readiness/proofs",
        json=failed_body,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert failed.status_code == 200
    failed_item = next(
        item
        for item in failed.json()["data"]["readiness"]["items"]
        if item["code"] == "critical_journeys"
    )
    assert failed_item["state"] == "blocker"
    assert db_session.query(LaunchReadinessProof).count() == 2


def test_launch_proof_rejects_sensitive_reference_and_platform_admin_write(client) -> None:
    owner_token = _login(client, "platform-owner@example.com", "pass-platform-owner")
    admin_token = _login(client, "platform-admin@example.com", "pass-platform-admin")
    now = datetime.now(UTC)
    body = {
        "gate_code": "known_limitations",
        "result": "passed",
        "proof_kind": "capability_review",
        "summary": "The public capability list was checked against current production behavior.",
        "evidence_reference": "https://example.com/private-receipt",
        "observed_at": now.isoformat(),
        "expires_at": (now + timedelta(days=30)).isoformat(),
    }

    rejected = client.post(
        "/api/v1/system/launch-readiness/proofs",
        json=body,
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert rejected.status_code == 400
    assert (
        rejected.json()["errors"][0]["details"]["reason_code"]
        == "launch_proof_sensitive_value_rejected"
    )

    body["evidence_reference"] = "CAPABILITY-REVIEW-2026-08"
    forbidden = client.post(
        "/api/v1/system/launch-readiness/proofs",
        json=body,
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert forbidden.status_code == 403


def test_owner_decision_is_append_only_and_stales_when_evidence_changes(client, db_session) -> None:
    token = _login(client, "platform-owner@example.com", "pass-platform-owner")
    now = datetime.now(UTC)
    decision_body = {
        "decision": "no_go",
        "release_reference": "LAUNCH-REVIEW-2026-08",
        "rationale": "Current saved evidence still contains launch blockers and incomplete live proof.",
        "known_limitations_acknowledged": False,
        "support_owner_confirmed": False,
        "rollback_owner_confirmed": False,
        "evidence_current_confirmed": True,
    }
    first = client.post(
        "/api/v1/system/launch-readiness/decisions",
        json=decision_body,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert first.status_code == 200
    assert first.json()["data"]["created"] is True
    assert first.json()["data"]["decision"]["current"] is True
    assert first.json()["data"]["readiness"]["latest_decision"]["decision"] == "no_go"

    repeat = client.post(
        "/api/v1/system/launch-readiness/decisions",
        json=decision_body,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert repeat.status_code == 200
    assert repeat.json()["data"]["created"] is False
    assert db_session.query(LaunchReadinessDecision).count() == 1

    proof_body = {
        "gate_code": "critical_journeys",
        "result": "passed",
        "proof_kind": "production_smoke",
        "summary": "The latest production customer journey completed with expected saved evidence.",
        "evidence_reference": "RELEASE-EVIDENCE-2026-08-21",
        "observed_at": now.isoformat(),
        "expires_at": (now + timedelta(days=30)).isoformat(),
    }
    changed = client.post(
        "/api/v1/system/launch-readiness/proofs",
        json=proof_body,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert changed.status_code == 200
    assert changed.json()["data"]["readiness"]["latest_decision"]["current"] is False
    assert db_session.query(LaunchReadinessDecision).count() == 1


def test_go_decision_fails_closed_until_every_gate_is_ready(client) -> None:
    token = _login(client, "platform-owner@example.com", "pass-platform-owner")
    response = client.post(
        "/api/v1/system/launch-readiness/decisions",
        json={
            "decision": "go",
            "release_reference": "LAUNCH-REVIEW-2026-08",
            "rationale": "Every required launch gate has current passing production evidence.",
            "known_limitations_acknowledged": True,
            "support_owner_confirmed": True,
            "rollback_owner_confirmed": True,
            "evidence_current_confirmed": True,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 409
    assert (
        response.json()["errors"][0]["details"]["reason_code"]
        == "launch_decision_evidence_not_ready"
    )
