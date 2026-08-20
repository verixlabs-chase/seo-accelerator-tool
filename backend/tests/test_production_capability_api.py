from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models.production_capability import ProductionCapabilityProof
from app.models.user import User
from app.services.commercial_plan_service import FEATURES
from app.services.production_capability_service import (
    build_production_capability_matrix,
    create_production_capability_proof,
)


def _login(client, email: str, password: str) -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def _body(*, result: str = "proven", limitation: str | None = None) -> dict:
    now = datetime.now(UTC)
    return {
        "capability_code": FEATURES[0].code,
        "result": result,
        "summary": "The current production journey completed with the expected customer result.",
        "customer_limitation": limitation,
        "evidence_reference": "CAPABILITY-RECEIPT-2026-08-01",
        "observed_at": now.isoformat(),
        "expires_at": (now + timedelta(days=30)).isoformat(),
    }


def test_capability_matrix_separates_catalog_inclusion_from_live_proof(client, db_session) -> None:
    owner_token = _login(client, "platform-owner@example.com", "pass-platform-owner")
    initial = client.get(
        "/api/v1/system/production-capabilities",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert initial.status_code == 200
    payload = initial.json()["data"]
    assert payload["evidence_state"] == "incomplete"
    assert payload["counts"]["needs_live_proof"] == len(FEATURES)
    item = payload["capabilities"][0]
    assert item["minimum_plan"] == "Solo"
    assert item["included_plans"] == ["Solo", "Growth", "Enterprise"]
    assert item["may_describe_as_available"] is False
    assert item["proof"] is None

    body = _body()
    first = client.post(
        "/api/v1/system/production-capabilities/proofs",
        json=body,
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert first.status_code == 200
    assert first.json()["data"]["created"] is True
    saved = first.json()["data"]["matrix"]["capabilities"][0]
    assert saved["claim_state"] == "proven"
    assert saved["may_describe_as_available"] is True

    repeat = client.post(
        "/api/v1/system/production-capabilities/proofs",
        json=body,
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert repeat.status_code == 200
    assert repeat.json()["data"]["created"] is False
    assert db_session.query(ProductionCapabilityProof).count() == 1


def test_limited_capability_requires_customer_limitation_and_owner_role(client) -> None:
    owner_token = _login(client, "platform-owner@example.com", "pass-platform-owner")
    admin_token = _login(client, "platform-admin@example.com", "pass-platform-admin")
    customer_token = _login(client, "org-admin@example.com", "pass-org-admin")

    missing = client.post(
        "/api/v1/system/production-capabilities/proofs",
        json=_body(result="limited"),
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert missing.status_code == 400
    assert (
        missing.json()["errors"][0]["details"]["reason_code"]
        == "production_capability_limitation_required"
    )

    body = _body(
        result="limited",
        limitation="Current production use supports saved reports only; scheduled delivery is not available.",
    )
    assert client.post(
        "/api/v1/system/production-capabilities/proofs",
        json=body,
        headers={"Authorization": f"Bearer {admin_token}"},
    ).status_code == 403
    assert client.get(
        "/api/v1/system/production-capabilities",
        headers={"Authorization": f"Bearer {customer_token}"},
    ).status_code == 403

    accepted = client.post(
        "/api/v1/system/production-capabilities/proofs",
        json=body,
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert accepted.status_code == 200
    item = accepted.json()["data"]["matrix"]["capabilities"][0]
    assert item["claim_state"] == "limited"
    assert item["must_show_limitation"] is True
    assert item["proof"]["customer_limitation"] == body["customer_limitation"]


def test_capability_proof_rejects_supplier_or_secret_shaped_content(client) -> None:
    owner_token = _login(client, "platform-owner@example.com", "pass-platform-owner")
    body = _body()
    body["summary"] = "The Google provider returned a successful production response for this feature."
    rejected = client.post(
        "/api/v1/system/production-capabilities/proofs",
        json=body,
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert rejected.status_code == 400
    assert (
        rejected.json()["errors"][0]["details"]["reason_code"]
        == "production_capability_sensitive_value_rejected"
    )


def test_sales_claim_gate_cannot_pass_with_an_incomplete_capability_matrix(client) -> None:
    owner_token = _login(client, "platform-owner@example.com", "pass-platform-owner")
    now = datetime.now(UTC)
    assert client.post(
        "/api/v1/system/launch-readiness/proofs",
        json={
            "gate_code": "known_limitations",
            "result": "passed",
            "proof_kind": "capability_review",
            "summary": "Current sales and help language was reviewed against the saved capability matrix.",
            "evidence_reference": "SALES-CLAIM-REVIEW-2026-08",
            "observed_at": now.isoformat(),
            "expires_at": (now + timedelta(days=30)).isoformat(),
        },
        headers={"Authorization": f"Bearer {owner_token}"},
    ).status_code == 200

    readiness = client.get(
        "/api/v1/system/launch-readiness",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert readiness.status_code == 200
    item = next(
        item
        for item in readiness.json()["data"]["items"]
        if item["code"] == "known_limitations"
    )
    assert item["state"] == "needs_live_proof"
    assert item["facts"]["missing_live_proof_count"] == len(FEATURES)
    assert "capability matrix is incomplete" in item["summary"].lower()


def test_expired_capability_receipt_becomes_stale_instead_of_remaining_available(
    db_session,
) -> None:
    user = db_session.query(User).filter(User.email == "platform-owner@example.com").one()
    now = datetime.now(UTC)
    proof, created = create_production_capability_proof(
        db_session,
        capability_code=FEATURES[0].code,
        result="proven",
        summary="The current production journey completed with the expected customer result.",
        customer_limitation=None,
        evidence_reference="CAPABILITY-EXPIRY-2026-08",
        observed_at=now,
        expires_at=now + timedelta(days=30),
        recorded_by_user_id=user.id,
        now=now,
    )
    assert created is True
    assert proof.result == "proven"

    matrix = build_production_capability_matrix(
        db_session,
        evaluated_at=now + timedelta(days=31),
    )
    item = matrix["capabilities"][0]
    assert item["claim_state"] == "stale"
    assert item["may_describe_as_available"] is False
    assert matrix["evidence_state"] == "incomplete"
