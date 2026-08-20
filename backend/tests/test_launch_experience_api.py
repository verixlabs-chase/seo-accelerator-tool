from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models.launch_experience import LaunchExperienceReview
from app.models.user import User
from app.services.launch_experience_service import (
    MODERATED_SUBJECT,
    ROUTE_CATALOG,
    build_launch_experience_readiness,
    create_launch_experience_review,
)
from app.services.launch_readiness_service import (
    build_launch_readiness,
    create_launch_readiness_proof,
)


def _login(client, email: str, password: str) -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def _body(**overrides) -> dict:
    now = datetime.now(UTC)
    body = {
        "review_kind": "route_audit",
        "subject_code": ROUTE_CATALOG[0][0],
        "viewport": "desktop",
        "result": "passed",
        "session_reference": None,
        "summary": "The complete route was understandable and recoverable in the tested viewport.",
        "issue_count": 0,
        "blocking_issue_count": 0,
        "evidence_reference": "EXPERIENCE-ROUTE-0001",
        "observed_at": now.isoformat(),
        "expires_at": (now + timedelta(days=30)).isoformat(),
    }
    body.update(overrides)
    return body


def test_launch_experience_route_review_is_owner_only_and_idempotent(client, db_session) -> None:
    owner = _login(client, "platform-owner@example.com", "pass-platform-owner")
    admin = _login(client, "platform-admin@example.com", "pass-platform-admin")
    customer = _login(client, "org-admin@example.com", "pass-org-admin")

    assert client.get(
        "/api/v1/system/launch-experience",
        headers={"Authorization": f"Bearer {admin}"},
    ).status_code == 200
    assert client.get(
        "/api/v1/system/launch-experience",
        headers={"Authorization": f"Bearer {customer}"},
    ).status_code == 403
    body = _body()
    assert client.post(
        "/api/v1/system/launch-experience/reviews",
        json=body,
        headers={"Authorization": f"Bearer {admin}"},
    ).status_code == 403

    first = client.post(
        "/api/v1/system/launch-experience/reviews",
        json=body,
        headers={"Authorization": f"Bearer {owner}"},
    )
    assert first.status_code == 200
    assert first.json()["data"]["created"] is True
    assert first.json()["data"]["readiness"]["route_audit"]["counts"]["missing"] == len(ROUTE_CATALOG)

    repeat = client.post(
        "/api/v1/system/launch-experience/reviews",
        json=body,
        headers={"Authorization": f"Bearer {owner}"},
    )
    assert repeat.status_code == 200
    assert repeat.json()["data"]["created"] is False
    assert db_session.query(LaunchExperienceReview).count() == 1


def test_moderated_session_requires_opaque_reference_and_rejects_sensitive_values(client) -> None:
    owner = _login(client, "platform-owner@example.com", "pass-platform-owner")
    invalid_alias = _body(
        review_kind="moderated_session",
        subject_code=MODERATED_SUBJECT,
        viewport="not_applicable",
        session_reference="person@example.com",
    )
    response = client.post(
        "/api/v1/system/launch-experience/reviews",
        json=invalid_alias,
        headers={"Authorization": f"Bearer {owner}"},
    )
    assert response.status_code == 400
    assert response.json()["errors"][0]["details"]["reason_code"] == "launch_experience_session_reference_invalid"

    supplier = _body(summary="The Google connection was clear and the complete first-use journey passed.")
    response = client.post(
        "/api/v1/system/launch-experience/reviews",
        json=supplier,
        headers={"Authorization": f"Bearer {owner}"},
    )
    assert response.status_code == 400
    assert response.json()["errors"][0]["details"]["reason_code"] == "launch_experience_sensitive_value_rejected"


def test_every_route_needs_both_viewports_and_five_distinct_sessions(db_session) -> None:
    user = db_session.query(User).filter(User.email == "platform-owner@example.com").one()
    now = datetime.now(UTC)
    for route_index, (code, _label, _path) in enumerate(ROUTE_CATALOG):
        for viewport in ("desktop", "mobile"):
            create_launch_experience_review(
                db_session,
                review_kind="route_audit",
                subject_code=code,
                viewport=viewport,
                result="passed",
                session_reference=None,
                summary="The route, its empty state, failure state, and recovery action were understandable.",
                issue_count=0,
                blocking_issue_count=0,
                evidence_reference=f"ROUTE-{route_index:02d}-{viewport.upper()}",
                observed_at=now,
                expires_at=now + timedelta(days=30),
                recorded_by_user_id=user.id,
                now=now,
            )
    route_ready = build_launch_experience_readiness(db_session, evaluated_at=now)
    assert route_ready["route_audit"]["evidence_state"] == "ready"
    assert route_ready["moderated_sessions"]["evidence_state"] == "incomplete"

    for index in range(5):
        create_launch_experience_review(
            db_session,
            review_kind="moderated_session",
            subject_code=MODERATED_SUBJECT,
            viewport="not_applicable",
            result="passed",
            session_reference=f"UX-{index:04d}",
            summary="The participant completed connection, baseline, next action, workflow, billing, and sign-out tasks.",
            issue_count=1,
            blocking_issue_count=0,
            evidence_reference=f"SESSION-RECEIPT-{index:04d}",
            observed_at=now,
            expires_at=now + timedelta(days=30),
            recorded_by_user_id=user.id,
            now=now,
        )
    ready = build_launch_experience_readiness(db_session, evaluated_at=now)
    assert ready["evidence_state"] == "ready"
    assert ready["route_audit"]["counts"]["passed"] == len(ROUTE_CATALOG)
    assert ready["moderated_sessions"]["counts"]["passed"] == 5

    reviewed_at = now + timedelta(minutes=1)
    for gate_code, proof_kind in (
        ("critical_journeys", "production_smoke"),
        ("first_use_comprehension", "moderated_test"),
    ):
        create_launch_readiness_proof(
            db_session,
            gate_code=gate_code,
            result="passed",
            proof_kind=proof_kind,
            summary="The completed structured evidence was reviewed and the production journey passed.",
            evidence_reference=f"FINAL-{gate_code.upper()}-REVIEW",
            observed_at=reviewed_at,
            expires_at=reviewed_at + timedelta(days=30),
            recorded_by_user_id=user.id,
            now=reviewed_at,
        )
    launch = build_launch_readiness(db_session, evaluated_at=reviewed_at)
    launch_gates = {item["code"]: item for item in launch["items"]}
    assert launch_gates["critical_journeys"]["state"] == "pass"
    assert launch_gates["first_use_comprehension"]["state"] == "pass"

    expired = build_launch_experience_readiness(
        db_session, evaluated_at=now + timedelta(days=31)
    )
    assert expired["evidence_state"] == "incomplete"
    assert expired["route_audit"]["counts"]["stale"] == len(ROUTE_CATALOG)
    assert expired["moderated_sessions"]["counts"]["stale"] == 5


def test_manual_launch_proofs_cannot_override_missing_structured_experience(client) -> None:
    owner = _login(client, "platform-owner@example.com", "pass-platform-owner")
    now = datetime.now(UTC)
    for gate_code, proof_kind in (
        ("critical_journeys", "production_smoke"),
        ("first_use_comprehension", "moderated_test"),
    ):
        response = client.post(
            "/api/v1/system/launch-readiness/proofs",
            json={
                "gate_code": gate_code,
                "result": "passed",
                "proof_kind": proof_kind,
                "summary": "The current production exercise completed with the expected customer result.",
                "evidence_reference": f"MANUAL-{gate_code.upper()}-2026",
                "observed_at": now.isoformat(),
                "expires_at": (now + timedelta(days=30)).isoformat(),
            },
            headers={"Authorization": f"Bearer {owner}"},
        )
        assert response.status_code == 200

    readiness = client.get(
        "/api/v1/system/launch-readiness",
        headers={"Authorization": f"Bearer {owner}"},
    ).json()["data"]
    gates = {item["code"]: item for item in readiness["items"]}
    assert gates["critical_journeys"]["state"] == "needs_live_proof"
    assert gates["critical_journeys"]["facts"]["required_viewport_count"] == len(ROUTE_CATALOG) * 2
    assert gates["first_use_comprehension"]["state"] == "needs_live_proof"
    assert gates["first_use_comprehension"]["facts"]["required_participant_count"] == 5
