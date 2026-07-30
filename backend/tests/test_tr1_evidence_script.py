from __future__ import annotations

from scripts.capture_tr1_operational_evidence import (
    capture_tr1_operational_evidence,
)


def test_tr1_evidence_captures_session_and_durable_job_truth(client) -> None:
    result = capture_tr1_operational_evidence(
        client,
        base_url="",
        email="platform-admin@example.com",
        password="pass-platform-admin",
    )

    assert result["passed"] is True
    assert result["secrets_logged"] is False
    assert result["durable_jobs"]["truth_scope"] == {
        "mode": "database",
        "durable": True,
        "multi_instance_safe": True,
    }
    assert [step["name"] for step in result["steps"]] == [
        "login",
        "authenticated_identity",
        "session_inventory",
        "refresh_rotation",
        "old_refresh_replay_blocked",
        "operational_health",
        "logout_revocation",
        "old_access_after_logout_blocked",
        "current_refresh_after_logout_blocked",
    ]
    assert all(step["passed"] for step in result["steps"])
