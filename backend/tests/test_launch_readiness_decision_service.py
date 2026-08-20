from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models.user import User
from app.services import launch_readiness_service


def _pass_item(code: str) -> dict:
    return launch_readiness_service._item(
        code=code,
        category="test",
        title=code,
        state=launch_readiness_service.PASS,
        summary="Current saved evidence passed.",
        evidence="Saved test evidence.",
        next_action="Keep it current.",
    )


def test_go_requires_ready_evidence_and_stales_after_new_failure(db_session, monkeypatch) -> None:
    user = db_session.query(User).filter(User.email == "platform-owner@example.com").one()
    now = datetime.now(UTC)
    for index, (gate_code, config) in enumerate(
        launch_readiness_service.MANUAL_GATE_CONFIG.items()
    ):
        row, created = launch_readiness_service.create_launch_readiness_proof(
            db_session,
            gate_code=gate_code,
            result="passed",
            proof_kind=config["proof_kind"],
            summary=f"Current production proof {index} completed with the expected saved result.",
            evidence_reference=f"READY-PROOF-{index}-2026-08",
            observed_at=now,
            expires_at=now + timedelta(days=30),
            recorded_by_user_id=user.id,
            now=now,
        )
        assert created is True
        assert row.gate_code == gate_code

    monkeypatch.setattr(
        launch_readiness_service,
        "_runtime_gate",
        lambda: _pass_item("production_runtime"),
    )
    monkeypatch.setattr(
        launch_readiness_service,
        "_billing_gate",
        lambda: _pass_item("billing_configuration"),
    )
    monkeypatch.setattr(
        launch_readiness_service,
        "_artifact_gate",
        lambda: _pass_item("durable_artifacts"),
    )
    monkeypatch.setattr(
        launch_readiness_service,
        "_provider_gate",
        lambda _db, *, now: _pass_item("provider_health"),
    )
    monkeypatch.setattr(
        launch_readiness_service,
        "_data_freshness_gate",
        lambda _db: _pass_item("data_freshness"),
    )
    monkeypatch.setattr(
        launch_readiness_service,
        "_support_queue_gate",
        lambda _db, *, now: _pass_item("support_queue"),
    )
    monkeypatch.setattr(
        launch_readiness_service,
        "build_production_capability_matrix",
        lambda _db, *, evaluated_at: {
            "evidence_state": "ready",
            "basis_digest": "a" * 64,
            "latest_observed_at": now.isoformat(),
            "counts": {
                "proven": 15,
                "limited": 0,
                "unavailable": 0,
                "stale": 0,
                "needs_live_proof": 0,
            },
            "capabilities": [{} for _ in range(15)],
        },
    )
    monkeypatch.setattr(
        launch_readiness_service,
        "build_launch_experience_readiness",
        lambda _db, *, evaluated_at: {
            "evidence_state": "ready",
            "basis_digest": "b" * 64,
            "route_audit": {
                "evidence_state": "ready",
                "required_route_count": 19,
                "required_viewport_count": 38,
                "latest_observed_at": now.isoformat(),
                "counts": {"passed": 19, "failed": 0, "stale": 0, "missing": 0},
            },
            "moderated_sessions": {
                "evidence_state": "ready",
                "latest_observed_at": now.isoformat(),
                "counts": {"passed": 5, "failed": 0, "stale": 0, "required": 5, "remaining": 0},
            },
        },
    )

    ready = launch_readiness_service.build_launch_readiness(db_session, evaluated_at=now)
    assert ready["evidence_state"] == "ready"
    assert ready["overall_state"] == "ready_for_decision"

    decision, created = launch_readiness_service.create_launch_readiness_decision(
        db_session,
        decision="go",
        release_reference="LAUNCH-READY-2026-08",
        rationale="Every current launch gate passed and the named operators confirmed closeout.",
        known_limitations_acknowledged=True,
        support_owner_confirmed=True,
        rollback_owner_confirmed=True,
        evidence_current_confirmed=True,
        decided_by_user_id=user.id,
        now=now,
    )
    assert created is True
    assert decision.decision == "go"
    current = launch_readiness_service.build_launch_readiness(db_session, evaluated_at=now)
    assert current["overall_state"] == "go"
    assert current["latest_decision"]["current"] is True

    gate_code = "critical_journeys"
    config = launch_readiness_service.MANUAL_GATE_CONFIG[gate_code]
    _, failure_created = launch_readiness_service.create_launch_readiness_proof(
        db_session,
        gate_code=gate_code,
        result="failed",
        proof_kind=config["proof_kind"],
        summary="The repeated production billing recovery journey failed to restore access.",
        evidence_reference="FAILED-PROOF-2026-08",
        observed_at=now + timedelta(minutes=1),
        expires_at=now + timedelta(days=30),
        recorded_by_user_id=user.id,
        now=now,
    )
    assert failure_created is True
    changed = launch_readiness_service.build_launch_readiness(
        db_session,
        evaluated_at=now + timedelta(minutes=1),
    )
    assert changed["overall_state"] == "no_go"
    assert changed["latest_decision"]["current"] is False
