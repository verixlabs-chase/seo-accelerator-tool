from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.customer_relay import insightos_local_relay as agent
from app.models.organization import Organization
from app.models.user import User
from app.services.commercial_plan_service import apply_commercial_plan


TOKEN = "iosr_" + "a" * 43


def _packet(*, now: datetime) -> dict:
    packet_id = "f8787d49-58d9-48bb-8f2d-2937039cdcdc"
    body = {
        "id": packet_id,
        "kind": agent.PACKET_KIND,
        "protocol_version": agent.PACKET_PROTOCOL_VERSION,
        "issued_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=5)).isoformat(),
        "artifact_hash": "b" * 64,
        "payload": {
            "challenge": "synthetic-challenge-1234567890",
            "expected_action": "acknowledge_synthetic_receipt",
            "response_hash_input": f"{packet_id}:<challenge>:received",
        },
        "safety": dict(agent.EXPECTED_SAFETY),
    }
    return {
        **body,
        "signature_algorithm": "hmac-sha256",
        "signature": agent.sign_payload(TOKEN, body),
        "acknowledge_path": f"/api/v1/ai/relay/packets/{packet_id}/acknowledge",
    }


def test_agent_builds_exact_signed_ack_for_synthetic_packet_only() -> None:
    now = datetime(2026, 8, 19, 15, 0, tzinfo=UTC)
    packet = _packet(now=now)

    path, acknowledgement = agent.build_acknowledgement(
        packet,
        token=TOKEN,
        now=now + timedelta(seconds=1),
    )

    expected_response = sha256(
        f"{packet['id']}:{packet['payload']['challenge']}:received".encode()
    ).hexdigest()
    assert path == packet["acknowledge_path"]
    assert acknowledgement["response_hash"] == expected_response
    assert acknowledgement["packet_artifact_hash"] == packet["artifact_hash"]
    assert acknowledgement["signature"] == agent.sign_payload(
        TOKEN,
        {
            "packet_id": packet["id"],
            "packet_artifact_hash": packet["artifact_hash"],
            "response_hash": expected_response,
        },
    )
    assert TOKEN not in json.dumps(acknowledgement)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda packet: packet.update(kind="customer_prompt"), "not a synthetic"),
        (
            lambda packet: packet["safety"].update(model_execution_requested=True),
            "customer or business work",
        ),
        (lambda packet: packet["payload"].update(prompt="hidden"), "challenge shape"),
        (lambda packet: packet.update(signature="0" * 64), "invalid signature"),
    ],
)
def test_agent_refuses_changed_or_executable_packets(mutation, message: str) -> None:
    now = datetime(2026, 8, 19, 15, 0, tzinfo=UTC)
    packet = _packet(now=now)
    mutation(packet)

    with pytest.raises(agent.RelayAgentError, match=message):
        agent.build_acknowledgement(
            packet,
            token=TOKEN,
            now=now + timedelta(seconds=1),
        )


def test_agent_refuses_expired_packet_and_insecure_remote_origin() -> None:
    now = datetime(2026, 8, 19, 15, 0, tzinfo=UTC)
    with pytest.raises(agent.RelayAgentError, match="validity window"):
        agent.build_acknowledgement(
            _packet(now=now),
            token=TOKEN,
            now=now + timedelta(minutes=6),
        )
    with pytest.raises(agent.RelayAgentError, match="requires HTTPS"):
        agent.validate_base_url("http://example.com")
    assert agent.validate_base_url("http://127.0.0.1:8000") == "http://127.0.0.1:8000"
    assert agent.validate_base_url("https://insightos.verixlabs.com/") == (
        "https://insightos.verixlabs.com"
    )


def test_agent_poll_once_uses_only_heartbeat_and_exact_ack(monkeypatch) -> None:
    now = datetime(2026, 8, 19, 15, 0, tzinfo=UTC)
    packet = _packet(now=now)
    calls: list[tuple[str, dict]] = []

    def fake_post_json(url, *, token, payload, timeout_seconds):  # noqa: ANN001
        assert token == TOKEN
        assert timeout_seconds == 15.0
        calls.append((url, payload))
        if url.endswith("/heartbeat"):
            return {
                "data": {
                    "accepted": True,
                    "protocol_version": agent.HEARTBEAT_PROTOCOL_VERSION,
                    "safety": dict(agent.EXPECTED_HEARTBEAT_SAFETY),
                    "work": [packet],
                }
            }
        return {
            "data": {
                "state": "verified",
                "safety": dict(agent.EXPECTED_ACKNOWLEDGEMENT_SAFETY),
            }
        }

    monkeypatch.setattr(agent, "post_json", fake_post_json)
    result = agent.poll_once(
        base_url="https://insightos.verixlabs.com",
        token=TOKEN,
        now=now + timedelta(seconds=1),
    )

    assert result == "diagnostic_verified"
    assert calls[0] == ("https://insightos.verixlabs.com/api/v1/ai/relay/heartbeat", {})
    assert calls[1][0] == packet["acknowledge_path"].replace(
        "/api/v1", "https://insightos.verixlabs.com/api/v1"
    )
    assert TOKEN not in json.dumps(calls)


def test_agent_refuses_heartbeat_that_enables_customer_work(monkeypatch) -> None:
    unsafe = dict(agent.EXPECTED_HEARTBEAT_SAFETY)
    unsafe["customer_prompts_allowed"] = True

    def fake_post_json(*_args, **_kwargs):
        return {
            "data": {
                "accepted": True,
                "protocol_version": agent.HEARTBEAT_PROTOCOL_VERSION,
                "safety": unsafe,
                "work": [],
            }
        }

    monkeypatch.setattr(agent, "post_json", fake_post_json)
    with pytest.raises(agent.RelayAgentError, match="did not confirm"):
        agent.poll_once(
            base_url="https://insightos.verixlabs.com",
            token=TOKEN,
        )


def test_agent_discovers_loopback_runtimes_but_never_returns_model_names() -> None:
    responses = {
        agent.DEFAULT_OLLAMA_URL: {
            "models": [{"name": "private-ollama-name"}, {"name": "second-name"}]
        },
        agent.DEFAULT_LM_STUDIO_URL: {
            "data": [{"id": "private-lm-studio-name"}]
        },
    }
    discovery = agent.discover_local_runtimes(probe=lambda url: responses[url])

    assert discovery == {
        "agent_version": "1.1.0",
        "runtime_kind": "multiple",
        "model_count": 3,
        "ollama_detected": True,
        "lm_studio_detected": True,
        "loopback_only": True,
        "customer_data_sent": False,
        "model_called": False,
        "model_identifiers_included": False,
    }
    serialized = json.dumps(discovery)
    assert "private-ollama-name" not in serialized
    assert "private-lm-studio-name" not in serialized
    with pytest.raises(agent.RelayAgentError, match="loopback"):
        agent.discover_local_runtimes(ollama_url="http://example.com/api/tags")


def test_agent_signs_exact_minimized_runtime_report(monkeypatch) -> None:
    now = datetime(2026, 8, 19, 16, 0, tzinfo=UTC)
    discovery = agent.discover_local_runtimes(probe=lambda _url: None)
    captured: dict = {}

    def fake_post_json(url, *, token, payload, timeout_seconds):  # noqa: ANN001
        captured.update(url=url, token=token, payload=payload, timeout=timeout_seconds)
        return {"data": {"accepted": True, "item": {**discovery, "id": payload["discovery_id"]}}}

    monkeypatch.setattr(agent, "post_json", fake_post_json)
    result = agent.report_runtime_discovery(
        base_url="https://insightos.verixlabs.com",
        token=TOKEN,
        discovery=discovery,
        now=now,
    )

    signed = {key: value for key, value in captured["payload"].items() if key != "signature"}
    assert captured["url"].endswith("/api/v1/ai/relay/runtime-discovery")
    assert captured["payload"]["signature"] == agent.sign_payload(TOKEN, signed)
    assert result["model_called"] is False
    assert TOKEN not in json.dumps(captured["payload"])


def test_agent_source_limits_model_execution_to_explicit_synthetic_endpoints() -> None:
    source = Path(agent.__file__).read_text(encoding="utf-8")
    assert "/api/generate" in source
    assert "/v1/chat/completions" in source
    assert "/v1/completions\"" not in source
    assert "--check-model" in source
    assert "requires --once so it cannot repeat" in source
    assert '"customer_work_allowed": False' in source
    assert '"publishing_allowed": False' in source


def test_agent_qualifies_one_ollama_model_with_made_up_data_only() -> None:
    local_calls: list[tuple[str, dict]] = []

    def probe(url):  # noqa: ANN001
        if url == agent.DEFAULT_OLLAMA_URL:
            return {"models": [{"name": "customer-private-model-name"}]}
        return {"data": []}

    def invoke(url, *, payload, timeout_seconds):  # noqa: ANN001
        local_calls.append((url, payload))
        assert timeout_seconds == 120.0
        return {"response": json.dumps(agent.MODEL_QUALIFICATION_EXPECTED)}

    result = agent.qualify_local_model(token=TOKEN, probe=probe, invoke=invoke)

    assert result["status"] == "passed"
    assert result["runtime_kind"] == "ollama"
    assert result["model_call_attempted"] is True
    assert result["model_response_received"] is True
    assert result["customer_data_sent"] is False
    assert result["raw_model_identifier_sent"] is False
    assert result["model_output_sent"] is False
    assert result["customer_work_allowed"] is False
    assert result["publishing_allowed"] is False
    assert "customer-private-model-name" not in json.dumps(result)
    assert agent.MODEL_QUALIFICATION_PROMPT in local_calls[0][1]["prompt"]
    assert local_calls[0][0].endswith("/api/generate")


def test_agent_reports_only_minimized_signed_model_qualification(monkeypatch) -> None:
    now = datetime(2026, 8, 19, 17, 0, tzinfo=UTC)
    qualification = {
        "agent_version": agent.AGENT_VERSION,
        "runtime_kind": "lm_studio",
        "local_model_fingerprint": "c" * 64,
        "prompt_version": agent.MODEL_QUALIFICATION_PROMPT_VERSION,
        "status": "passed",
        "latency_ms": 42,
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
    }
    captured: dict = {}

    def fake_post_json(url, *, token, payload, timeout_seconds):  # noqa: ANN001
        captured.update(url=url, token=token, payload=payload, timeout=timeout_seconds)
        return {
            "data": {
                "accepted": True,
                "item": {**qualification, "id": payload["qualification_id"]},
            }
        }

    monkeypatch.setattr(agent, "post_json", fake_post_json)
    result = agent.report_model_qualification(
        base_url="https://insightos.verixlabs.com",
        token=TOKEN,
        qualification=qualification,
        now=now,
    )

    signed = {key: value for key, value in captured["payload"].items() if key != "signature"}
    assert captured["url"].endswith("/api/v1/ai/relay/model-qualification")
    assert captured["payload"]["signature"] == agent.sign_payload(TOKEN, signed)
    assert "model_name" not in captured["payload"]
    assert "output" not in captured["payload"]
    assert "prompt" not in captured["payload"]
    assert result["status"] == "passed"


def test_agent_requires_one_shot_for_model_check(monkeypatch, capsys) -> None:
    monkeypatch.setenv("INSIGHTOS_RELAY_TOKEN", TOKEN)
    assert agent.main(["--check-model"]) == 2
    assert "requires --once" in capsys.readouterr().err


def test_authenticated_enterprise_owner_can_download_dependency_free_agent(
    client,
    db_session: Session,
) -> None:
    actor = db_session.query(User).filter(User.email == "a@example.com").one()
    organization = db_session.get(Organization, actor.tenant_id)
    assert organization is not None
    apply_commercial_plan(
        db_session,
        organization_id=organization.id,
        plan_code="enterprise",
    )
    db_session.commit()
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "org-owner@example.com", "password": "pass-org-owner"},
    )
    headers = {"Authorization": f"Bearer {login.json()['data']['access_token']}"}
    response = client.get(
        "/api/v1/ai/relay-enrollments/agent/download",
        headers=headers,
    )

    assert response.status_code == 200
    assert "insightos-local-relay.py" in response.headers["content-disposition"]
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-sha256"] == sha256(response.content).hexdigest()
    source = response.content.decode("utf-8")
    compile(source, "insightos-local-relay.py", "exec")
    assert "INSIGHTOS_RELAY_TOKEN" in source
    assert "requests" not in source
    assert "openai" not in source.lower()
    assert "Customer prompts and business work are disabled" in source
    assert "--check-model" in source
