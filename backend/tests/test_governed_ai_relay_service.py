from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
import hmac
import json

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.governed_ai_relay import GovernedAIRelayEnrollment
from app.models.governed_ai_relay_packet import (
    GovernedAIRelayDiagnosticAcknowledgement,
    GovernedAIRelayDiagnosticPacket,
)
from app.models.governed_ai_relay_qualification import (
    GovernedAIRelayModelQualification,
)
from app.models.governed_ai_relay_runtime import GovernedAIRelayRuntimeDiscovery
from app.models.organization import Organization
from app.models.user import User
from app.services.commercial_plan_service import (
    CommercialPlanFeatureDenied,
    apply_commercial_plan,
)
from app.services.governed_ai_relay_service import (
    GovernedAIRelayError,
    acknowledge_relay_diagnostic_packet,
    create_relay_diagnostic_packet,
    create_relay_enrollment,
    list_relay_enrollments,
    record_relay_heartbeat,
    record_relay_model_qualification,
    record_relay_runtime_discovery,
    revoke_relay_enrollment,
)


ACKNOWLEDGEMENTS = {
    "understands_connection_only": True,
    "understands_no_customer_prompts": True,
    "understands_no_database_or_execution_access": True,
    "understands_manual_revocation": True,
}


def _signature(token: str, payload: dict[str, str]) -> str:
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return hmac.new(token.encode(), canonical.encode(), sha256).hexdigest()


def _runtime_payload(*, observed_at: datetime) -> dict:
    return {
        "discovery_id": "64c71ef1-54a1-4f2b-b67d-8eb4a0a7a107",
        "agent_version": "1.1.0",
        "runtime_kind": "multiple",
        "model_count": 3,
        "ollama_detected": True,
        "lm_studio_detected": True,
        "loopback_only": True,
        "customer_data_sent": False,
        "model_called": False,
        "model_identifiers_included": False,
        "observed_at": observed_at.isoformat(),
    }


def _qualification_payload(*, observed_at: datetime) -> dict:
    return {
        "qualification_id": "12a8ecdb-552a-41c5-a89b-637c068ad8c7",
        "agent_version": "1.1.0",
        "runtime_kind": "ollama",
        "local_model_fingerprint": "c" * 64,
        "prompt_version": "local-model-synthetic-v1",
        "status": "passed",
        "latency_ms": 77,
        "output_json_valid": True,
        "required_contract_matched": True,
        "synthetic_input_only": True,
        "model_call_attempted": True,
        "model_response_received": True,
        "customer_data_sent": False,
        "raw_model_identifier_sent": False,
        "model_output_sent": False,
        "customer_work_allowed": False,
        "publishing_allowed": False,
        "observed_at": observed_at.isoformat(),
    }


def test_runtime_discovery_is_signed_minimized_idempotent_and_customer_safe(
    client,
    db_session: Session,
) -> None:
    organization, actor = _enterprise_owner(db_session)
    now = datetime(2026, 8, 19, 16, 0, tzinfo=UTC)
    enrollment = create_relay_enrollment(
        db_session,
        organization_id=organization.id,
        actor_user_id=actor.id,
        name="Office local model",
        client_request_id="runtime-discovery-enrollment",
        acknowledgements=ACKNOWLEDGEMENTS,
        now=now,
    )
    token = str(enrollment["enrollment_token"])
    payload = _runtime_payload(observed_at=now)
    signature = _signature(token, payload)

    result = record_relay_runtime_discovery(
        db_session,
        bearer_token=token,
        signature=signature,
        now=now + timedelta(seconds=10),
        **{**payload, "observed_at": now},
    )
    repeated = record_relay_runtime_discovery(
        db_session,
        bearer_token=token,
        signature=signature,
        now=now + timedelta(seconds=20),
        **{**payload, "observed_at": now},
    )
    assert result["created"] is True
    assert repeated["created"] is False
    assert result["item"]["runtime_kind"] == "multiple"
    assert result["item"]["model_count"] == 3
    serialized = json.dumps(result)
    assert "model-a" not in serialized
    assert "request_signature_hash" not in serialized
    assert db_session.query(GovernedAIRelayRuntimeDiscovery).count() == 1
    saved = db_session.query(GovernedAIRelayRuntimeDiscovery).one()
    assert saved.request_signature_hash != signature
    saved.model_called = True
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "org-owner@example.com", "password": "pass-org-owner"},
    )
    headers = {"Authorization": f"Bearer {login.json()['data']['access_token']}"}
    listed = client.get("/api/v1/ai/relay-enrollments", headers=headers)
    runtime = listed.json()["data"]["runtime_discovery"]
    assert runtime["runtime_kind"] == "multiple"
    assert runtime["model_identifiers_included"] is False
    assert "artifact_hash" not in runtime


def test_runtime_discovery_api_rejects_bad_signature_and_changed_safety(
    client,
    db_session: Session,
) -> None:
    organization, actor = _enterprise_owner(db_session)
    now = datetime.now(UTC)
    enrollment = create_relay_enrollment(
        db_session,
        organization_id=organization.id,
        actor_user_id=actor.id,
        name="Office local model",
        client_request_id="runtime-discovery-api-enrollment",
        acknowledgements=ACKNOWLEDGEMENTS,
        now=now,
    )
    token = str(enrollment["enrollment_token"])
    payload = _runtime_payload(observed_at=now)
    response = client.post(
        "/api/v1/ai/relay/runtime-discovery",
        headers={"Authorization": f"Bearer {token}"},
        json={**payload, "signature": _signature(token, payload)},
    )
    assert response.status_code == 200
    assert response.json()["data"]["item"]["model_called"] is False

    changed = {**payload, "discovery_id": "64c71ef1-54a1-4f2b-b67d-8eb4a0a7a108", "model_called": True}
    rejected = client.post(
        "/api/v1/ai/relay/runtime-discovery",
        headers={"Authorization": f"Bearer {token}"},
        json={**changed, "signature": _signature(token, changed)},
    )
    assert rejected.status_code == 422
    bad_signature_payload = {
        **payload,
        "discovery_id": "64c71ef1-54a1-4f2b-b67d-8eb4a0a7a109",
    }
    bad_signature = client.post(
        "/api/v1/ai/relay/runtime-discovery",
        headers={"Authorization": f"Bearer {token}"},
        json={**bad_signature_payload, "signature": "0" * 64},
    )
    assert bad_signature.status_code == 401
    stale_at = now - timedelta(minutes=10)
    stale_payload = {
        **payload,
        "discovery_id": "64c71ef1-54a1-4f2b-b67d-8eb4a0a7a110",
        "observed_at": stale_at.isoformat(),
    }
    stale = client.post(
        "/api/v1/ai/relay/runtime-discovery",
        headers={"Authorization": f"Bearer {token}"},
        json={**stale_payload, "signature": _signature(token, stale_payload)},
    )
    assert stale.status_code == 422
    assert db_session.query(GovernedAIRelayRuntimeDiscovery).count() == 1


def test_model_qualification_is_signed_minimized_and_enables_nothing(
    client,
    db_session: Session,
) -> None:
    organization, actor = _enterprise_owner(db_session)
    now = datetime(2026, 8, 19, 17, 0, tzinfo=UTC)
    enrollment = create_relay_enrollment(
        db_session,
        organization_id=organization.id,
        actor_user_id=actor.id,
        name="Office local model",
        client_request_id="model-qualification-enrollment",
        acknowledgements=ACKNOWLEDGEMENTS,
        now=now,
    )
    token = str(enrollment["enrollment_token"])
    payload = _qualification_payload(observed_at=now)
    signature = _signature(token, payload)
    call_payload = {**payload, "observed_at": now}

    result = record_relay_model_qualification(
        db_session,
        bearer_token=token,
        signature=signature,
        now=now + timedelta(seconds=10),
        **call_payload,
    )
    repeated = record_relay_model_qualification(
        db_session,
        bearer_token=token,
        signature=signature,
        now=now + timedelta(seconds=20),
        **call_payload,
    )

    assert result["created"] is True
    assert repeated["created"] is False
    item = result["item"]
    assert item["status"] == "passed"
    assert item["synthetic_input_only"] is True
    assert item["model_call_attempted"] is True
    assert item["model_response_received"] is True
    assert item["customer_data_sent"] is False
    assert item["raw_model_identifier_sent"] is False
    assert item["model_output_sent"] is False
    assert item["customer_work_allowed"] is False
    assert item["publishing_allowed"] is False
    serialized = json.dumps(result)
    assert "local_model_fingerprint" not in serialized
    assert "request_signature_hash" not in serialized
    assert "model_name" not in serialized
    assert '"model_output":' not in serialized
    assert db_session.query(GovernedAIRelayModelQualification).count() == 1
    saved = db_session.query(GovernedAIRelayModelQualification).one()
    saved.customer_work_allowed = True
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "org-owner@example.com", "password": "pass-org-owner"},
    )
    headers = {"Authorization": f"Bearer {login.json()['data']['access_token']}"}
    listed = client.get("/api/v1/ai/relay-enrollments", headers=headers)
    summary = listed.json()["data"]["model_qualification"]
    assert summary["status"] == "passed"
    assert summary["truth"]["state"] == "qualification_only"
    assert "fingerprint" not in json.dumps(summary)


def test_model_qualification_api_rejects_non_synthetic_or_bad_signature(
    client,
    db_session: Session,
) -> None:
    organization, actor = _enterprise_owner(db_session)
    now = datetime.now(UTC)
    enrollment = create_relay_enrollment(
        db_session,
        organization_id=organization.id,
        actor_user_id=actor.id,
        name="Office local model",
        client_request_id="model-qualification-api-enrollment",
        acknowledgements=ACKNOWLEDGEMENTS,
        now=now,
    )
    token = str(enrollment["enrollment_token"])
    payload = _qualification_payload(observed_at=now)
    response = client.post(
        "/api/v1/ai/relay/model-qualification",
        headers={"Authorization": f"Bearer {token}"},
        json={**payload, "signature": _signature(token, payload)},
    )
    assert response.status_code == 200

    unsafe = {
        **payload,
        "qualification_id": "12a8ecdb-552a-41c5-a89b-637c068ad8c8",
        "customer_data_sent": True,
    }
    unsafe_response = client.post(
        "/api/v1/ai/relay/model-qualification",
        headers={"Authorization": f"Bearer {token}"},
        json={**unsafe, "signature": _signature(token, unsafe)},
    )
    assert unsafe_response.status_code == 422
    bad_signature = {
        **payload,
        "qualification_id": "12a8ecdb-552a-41c5-a89b-637c068ad8c9",
    }
    bad_response = client.post(
        "/api/v1/ai/relay/model-qualification",
        headers={"Authorization": f"Bearer {token}"},
        json={**bad_signature, "signature": "0" * 64},
    )
    assert bad_response.status_code == 401
    assert db_session.query(GovernedAIRelayModelQualification).count() == 1


def _enterprise_owner(db: Session) -> tuple[Organization, User]:
    actor = db.query(User).filter(User.email == "a@example.com").one()
    organization = db.get(Organization, actor.tenant_id)
    assert organization is not None
    apply_commercial_plan(
        db,
        organization_id=organization.id,
        plan_code="enterprise",
    )
    db.commit()
    return organization, actor


def test_relay_enrollment_heartbeat_and_revocation_stay_connection_only(
    db_session: Session,
) -> None:
    organization, actor = _enterprise_owner(db_session)
    started_at = datetime(2026, 8, 19, 12, 0, tzinfo=UTC)
    created = create_relay_enrollment(
        db_session,
        organization_id=organization.id,
        actor_user_id=actor.id,
        name="Office local model",
        client_request_id="relay-request-0001",
        acknowledgements=ACKNOWLEDGEMENTS,
        now=started_at,
    )
    token = str(created["enrollment_token"])
    enrollment_id = str(created["item"]["id"])

    assert token.startswith("iosr_")
    assert created["token_returned_once"] is True
    assert created["item"]["connection_state"] == "waiting_for_first_check"
    assert created["safety"] == {
        "customer_prompts_allowed": False,
        "decision_packets_enabled": False,
        "database_access_allowed": False,
        "execution_allowed": False,
        "publishing_allowed": False,
    }
    stored = db_session.get(GovernedAIRelayEnrollment, enrollment_id)
    assert stored is not None
    assert stored.token_hash != token
    assert token not in json.dumps(list_relay_enrollments(
        db_session,
        organization_id=organization.id,
        now=started_at,
    ))
    audit_payloads = " ".join(
        row.payload_json
        for row in db_session.query(AuditLog)
        .filter(AuditLog.event_type == "ai.local_relay.enrolled")
        .all()
    )
    assert token not in audit_payloads

    heartbeat = record_relay_heartbeat(
        db_session,
        bearer_token=token,
        now=started_at + timedelta(minutes=1),
    )
    assert heartbeat["accepted"] is True
    assert heartbeat["work"] == []
    assert heartbeat["truth"]["state"] == "connection_only"
    assert list_relay_enrollments(
        db_session,
        organization_id=organization.id,
        now=started_at + timedelta(minutes=2),
    )["current"]["connection_state"] == "connected"

    revoked = revoke_relay_enrollment(
        db_session,
        organization_id=organization.id,
        enrollment_id=enrollment_id,
        actor_user_id=actor.id,
        now=started_at + timedelta(minutes=3),
    )
    assert revoked["item"]["connection_state"] == "revoked"
    with pytest.raises(GovernedAIRelayError, match="invalid or revoked"):
        record_relay_heartbeat(
            db_session,
            bearer_token=token,
            now=started_at + timedelta(minutes=4),
        )


def test_relay_requires_all_owner_acknowledgements_and_enterprise_plan(
    db_session: Session,
) -> None:
    organization, actor = _enterprise_owner(db_session)
    missing_ack = {**ACKNOWLEDGEMENTS, "understands_no_customer_prompts": False}
    with pytest.raises(GovernedAIRelayError) as exc_info:
        create_relay_enrollment(
            db_session,
            organization_id=organization.id,
            actor_user_id=actor.id,
            name="Office local model",
            client_request_id="relay-request-0002",
            acknowledgements=missing_ack,
        )
    assert exc_info.value.reason_code == "relay_acknowledgements_required"
    assert db_session.query(GovernedAIRelayEnrollment).count() == 0


def test_growth_plan_cannot_create_or_operate_a_local_model_relay(
    client,
    db_session: Session,
) -> None:
    organization, actor = _enterprise_owner(db_session)
    now = datetime(2026, 8, 19, 18, 0, tzinfo=UTC)
    enrollment = create_relay_enrollment(
        db_session,
        organization_id=organization.id,
        actor_user_id=actor.id,
        name="Enterprise office model",
        client_request_id="relay-enterprise-tier-boundary",
        acknowledgements=ACKNOWLEDGEMENTS,
        now=now,
    )
    token = str(enrollment["enrollment_token"])
    enrollment_id = str(enrollment["item"]["id"])

    apply_commercial_plan(
        db_session,
        organization_id=organization.id,
        plan_code="multi_location",
    )
    db_session.commit()

    with pytest.raises(CommercialPlanFeatureDenied) as create_error:
        create_relay_enrollment(
            db_session,
            organization_id=organization.id,
            actor_user_id=actor.id,
            name="Growth model",
            client_request_id="relay-growth-tier-blocked",
            acknowledgements=ACKNOWLEDGEMENTS,
            now=now + timedelta(seconds=1),
        )
    assert create_error.value.reason_code == "private_ai_provider_upgrade_required"

    with pytest.raises(CommercialPlanFeatureDenied) as diagnostic_error:
        create_relay_diagnostic_packet(
            db_session,
            organization_id=organization.id,
            enrollment_id=enrollment_id,
            actor_user_id=actor.id,
            client_request_id="relay-growth-diagnostic-blocked",
            now=now + timedelta(seconds=2),
        )
    assert diagnostic_error.value.reason_code == "private_ai_provider_upgrade_required"

    for operation in (
        lambda: record_relay_heartbeat(
            db_session,
            bearer_token=token,
            now=now + timedelta(seconds=3),
        ),
        lambda: record_relay_runtime_discovery(
            db_session,
            bearer_token=token,
            signature="0" * 64,
            now=now + timedelta(seconds=4),
            **{
                **_runtime_payload(observed_at=now + timedelta(seconds=4)),
                "observed_at": now + timedelta(seconds=4),
            },
        ),
        lambda: record_relay_model_qualification(
            db_session,
            bearer_token=token,
            signature="0" * 64,
            now=now + timedelta(seconds=5),
            **{
                **_qualification_payload(observed_at=now + timedelta(seconds=5)),
                "observed_at": now + timedelta(seconds=5),
            },
        ),
    ):
        with pytest.raises(GovernedAIRelayError) as operation_error:
            operation()
        assert operation_error.value.reason_code == "relay_plan_unavailable"
        assert operation_error.value.status_code == 403

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "org-owner@example.com", "password": "pass-org-owner"},
    )
    headers = {"Authorization": f"Bearer {login.json()['data']['access_token']}"}
    download = client.get(
        "/api/v1/ai/relay-enrollments/agent/download",
        headers=headers,
    )
    assert download.status_code == 403
    assert (
        download.json()["errors"][0]["details"]["reason_code"]
        == "private_ai_provider_upgrade_required"
    )

    listed = list_relay_enrollments(
        db_session,
        organization_id=organization.id,
        now=now + timedelta(seconds=6),
    )
    assert listed["current"]["id"] == enrollment_id
    assert listed["current"]["connection_state"] != "connected"
    revoked = revoke_relay_enrollment(
        db_session,
        organization_id=organization.id,
        enrollment_id=enrollment_id,
        actor_user_id=actor.id,
        now=now + timedelta(seconds=7),
    )
    assert revoked["item"]["connection_state"] == "revoked"


def test_relay_api_returns_one_time_key_and_public_heartbeat_has_no_work(
    client,
    db_session: Session,
) -> None:
    organization, _actor = _enterprise_owner(db_session)
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "org-owner@example.com", "password": "pass-org-owner"},
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['data']['access_token']}"}
    response = client.post(
        "/api/v1/ai/relay-enrollments",
        headers=headers,
        json={
            "name": "Office local model",
            "client_request_id": "relay-api-request-0001",
            **ACKNOWLEDGEMENTS,
        },
    )
    assert response.status_code == 201
    payload = response.json()["data"]
    token = payload["enrollment_token"]
    assert payload["item"]["token_hint"] != token
    assert "token_hash" not in payload["item"]

    heartbeat = client.post(
        "/api/v1/ai/relay/heartbeat",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert heartbeat.status_code == 200
    heartbeat_data = heartbeat.json()["data"]
    assert heartbeat_data["work"] == []
    assert heartbeat_data["safety"]["database_access_allowed"] is False
    assert heartbeat_data["safety"]["execution_allowed"] is False

    list_response = client.get("/api/v1/ai/relay-enrollments", headers=headers)
    assert list_response.status_code == 200
    assert list_response.json()["data"]["current"]["name"] == "Office local model"
    assert organization.id not in json.dumps(heartbeat_data)


def test_signed_synthetic_packet_is_short_lived_single_use_and_runs_no_model(
    db_session: Session,
) -> None:
    organization, actor = _enterprise_owner(db_session)
    started_at = datetime(2026, 8, 19, 13, 0, tzinfo=UTC)
    enrollment = create_relay_enrollment(
        db_session,
        organization_id=organization.id,
        actor_user_id=actor.id,
        name="Office local model",
        client_request_id="relay-packet-enrollment-0001",
        acknowledgements=ACKNOWLEDGEMENTS,
        now=started_at,
    )
    token = str(enrollment["enrollment_token"])
    enrollment_id = str(enrollment["item"]["id"])
    created = create_relay_diagnostic_packet(
        db_session,
        organization_id=organization.id,
        enrollment_id=enrollment_id,
        actor_user_id=actor.id,
        client_request_id="relay-packet-request-0001",
        now=started_at + timedelta(seconds=5),
    )

    assert created["item"]["state"] == "waiting_for_relay"
    assert "challenge_nonce" not in created["item"]
    assert "expected_response_hash" not in created["item"]
    assert "artifact_hash" not in created["item"]
    assert "payload" not in created["item"]
    assert created["safety"] == {
        "customer_data_included": False,
        "model_execution_requested": False,
        "database_access_requested": False,
        "business_execution_requested": False,
        "publishing_requested": False,
    }
    heartbeat = record_relay_heartbeat(
        db_session,
        bearer_token=token,
        now=started_at + timedelta(seconds=10),
    )
    assert len(heartbeat["work"]) == 1
    packet = heartbeat["work"][0]
    unsigned_packet = {
        key: value
        for key, value in packet.items()
        if key not in {"signature", "signature_algorithm", "acknowledge_path"}
    }
    assert packet["signature"] == _signature(token, unsigned_packet)
    assert packet["kind"] == "synthetic_connection_challenge"
    assert packet["safety"]["customer_data_included"] is False
    assert packet["safety"]["model_execution_requested"] is False

    response_hash = sha256(
        f"{packet['id']}:{packet['payload']['challenge']}:received".encode()
    ).hexdigest()
    ack_payload = {
        "packet_id": packet["id"],
        "packet_artifact_hash": packet["artifact_hash"],
        "response_hash": response_hash,
    }
    acknowledgement = acknowledge_relay_diagnostic_packet(
        db_session,
        bearer_token=token,
        packet_id=packet["id"],
        packet_artifact_hash=packet["artifact_hash"],
        response_hash=response_hash,
        signature=_signature(token, ack_payload),
        now=started_at + timedelta(seconds=15),
    )
    assert acknowledgement["state"] == "verified"
    assert acknowledgement["created"] is True
    assert acknowledgement["safety"]["model_called"] is False
    assert db_session.query(GovernedAIRelayDiagnosticPacket).count() == 1
    assert db_session.query(GovernedAIRelayDiagnosticAcknowledgement).count() == 1
    saved_ack = db_session.query(GovernedAIRelayDiagnosticAcknowledgement).one()
    saved_ack.model_called = True
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
    assert record_relay_heartbeat(
        db_session,
        bearer_token=token,
        now=started_at + timedelta(seconds=45),
    )["work"] == []
    repeated = acknowledge_relay_diagnostic_packet(
        db_session,
        bearer_token=token,
        packet_id=packet["id"],
        packet_artifact_hash=packet["artifact_hash"],
        response_hash=response_hash,
        signature=_signature(token, ack_payload),
        now=started_at + timedelta(seconds=50),
    )
    assert repeated["created"] is False
    late_replay = acknowledge_relay_diagnostic_packet(
        db_session,
        bearer_token=token,
        packet_id=packet["id"],
        packet_artifact_hash=packet["artifact_hash"],
        response_hash=response_hash,
        signature=_signature(token, ack_payload),
        now=started_at + timedelta(minutes=6),
    )
    assert late_replay["created"] is False
    assert db_session.query(GovernedAIRelayDiagnosticAcknowledgement).count() == 1


def test_synthetic_packet_rejects_bad_signature_and_expired_ack(
    db_session: Session,
) -> None:
    organization, actor = _enterprise_owner(db_session)
    started_at = datetime(2026, 8, 19, 14, 0, tzinfo=UTC)
    enrollment = create_relay_enrollment(
        db_session,
        organization_id=organization.id,
        actor_user_id=actor.id,
        name="Office local model",
        client_request_id="relay-packet-enrollment-0002",
        acknowledgements=ACKNOWLEDGEMENTS,
        now=started_at,
    )
    token = str(enrollment["enrollment_token"])
    created = create_relay_diagnostic_packet(
        db_session,
        organization_id=organization.id,
        enrollment_id=str(enrollment["item"]["id"]),
        actor_user_id=actor.id,
        client_request_id="relay-packet-request-0002",
        now=started_at,
    )
    packet_id = str(created["item"]["id"])
    packet = db_session.get(GovernedAIRelayDiagnosticPacket, packet_id)
    assert packet is not None

    with pytest.raises(GovernedAIRelayError) as signature_error:
        acknowledge_relay_diagnostic_packet(
            db_session,
            bearer_token=token,
            packet_id=packet.id,
            packet_artifact_hash=packet.artifact_hash,
            response_hash=packet.expected_response_hash,
            signature="0" * 64,
            now=started_at + timedelta(minutes=1),
        )
    assert signature_error.value.reason_code == "relay_diagnostic_signature_invalid"
    with pytest.raises(GovernedAIRelayError) as expired_error:
        ack_payload = {
            "packet_id": packet.id,
            "packet_artifact_hash": packet.artifact_hash,
            "response_hash": packet.expected_response_hash,
        }
        acknowledge_relay_diagnostic_packet(
            db_session,
            bearer_token=token,
            packet_id=packet.id,
            packet_artifact_hash=packet.artifact_hash,
            response_hash=packet.expected_response_hash,
            signature=_signature(token, ack_payload),
            now=started_at + timedelta(minutes=6),
        )
    assert expired_error.value.reason_code == "relay_diagnostic_expired"
    assert db_session.query(GovernedAIRelayDiagnosticAcknowledgement).count() == 0


def test_relay_api_round_trips_one_signed_synthetic_packet(
    client,
    db_session: Session,
) -> None:
    _organization, _actor = _enterprise_owner(db_session)
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "org-owner@example.com", "password": "pass-org-owner"},
    )
    headers = {"Authorization": f"Bearer {login.json()['data']['access_token']}"}
    enrollment_response = client.post(
        "/api/v1/ai/relay-enrollments",
        headers=headers,
        json={
            "name": "Office local model",
            "client_request_id": "relay-api-packet-enrollment-0001",
            **ACKNOWLEDGEMENTS,
        },
    )
    enrollment_data = enrollment_response.json()["data"]
    token = enrollment_data["enrollment_token"]
    enrollment_id = enrollment_data["item"]["id"]
    packet_response = client.post(
        f"/api/v1/ai/relay-enrollments/{enrollment_id}/diagnostic-packets",
        headers=headers,
        json={"client_request_id": "relay-api-packet-request-0001"},
    )
    assert packet_response.status_code == 201
    assert packet_response.json()["data"]["item"]["state"] == "waiting_for_relay"

    heartbeat = client.post(
        "/api/v1/ai/relay/heartbeat",
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]
    packet = heartbeat["work"][0]
    response_hash = sha256(
        f"{packet['id']}:{packet['payload']['challenge']}:received".encode()
    ).hexdigest()
    ack_payload = {
        "packet_id": packet["id"],
        "packet_artifact_hash": packet["artifact_hash"],
        "response_hash": response_hash,
    }
    acknowledged = client.post(
        packet["acknowledge_path"],
        headers={"Authorization": f"Bearer {token}"},
        json={
            "packet_artifact_hash": packet["artifact_hash"],
            "response_hash": response_hash,
            "signature": _signature(token, ack_payload),
        },
    )
    assert acknowledged.status_code == 200
    assert acknowledged.json()["data"]["state"] == "verified"
    assert client.post(
        "/api/v1/ai/relay/heartbeat",
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]["work"] == []
