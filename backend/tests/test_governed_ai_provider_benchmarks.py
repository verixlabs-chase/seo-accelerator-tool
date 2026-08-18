from __future__ import annotations

import base64
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
import json
from types import SimpleNamespace
import socket

import pytest
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.campaign import Campaign
from app.models.governed_ai import GovernedAIRun
from app.models.governed_ai_provider_benchmark import GovernedAIProviderBenchmark
from app.models.governed_ai_provider_canary import (
    GovernedAIProviderCanaryAttempt,
    GovernedAIProviderCanaryEvent,
    GovernedAIProviderCanaryHealthSnapshot,
)
from app.models.governed_ai_provider_connection import GovernedAIProviderConnection
from app.models.governed_ai_provider_capability import (
    GovernedAIProviderCapabilityAttempt,
    GovernedAIProviderCapabilityBenchmark,
    GovernedAIProviderCapabilityEvent,
)
from app.models.governed_ai_provider_review import GovernedAIProviderReview
from app.models.governed_ai_provider_routing_readiness import (
    GovernedAIProviderRoutingReadiness,
)
from app.models.governed_ai_provider_standby_event import (
    GovernedAIProviderStandbyEvent,
)
from app.models.organization import Organization
from app.models.user import User
from app.services.commercial_plan_service import apply_commercial_plan
from app.services.governed_ai_provider_benchmark_service import (
    list_provider_benchmarks,
    run_provider_benchmark,
)
from app.services.governed_ai_provider_connection_service import (
    GovernedAIProviderConnectionError,
    ProviderValidationHTTPResult,
    create_provider_connection,
    validate_provider_connection,
)
from app.services.governed_ai_provider_review_service import (
    list_provider_reviews,
    review_provider_benchmark,
)
from app.services.governed_ai_provider_standby_service import (
    list_provider_standby_events,
    set_provider_standby,
)
from app.services.governed_ai_provider_readiness_service import (
    check_provider_routing_readiness,
    list_provider_routing_readiness,
)
from app.services.governed_ai_provider_canary_service import (
    automatic_rollback,
    authorize_canary_dispatch,
    create_canary_monitoring_snapshot,
    list_canary_monitoring,
    list_provider_canary,
    record_managed_fallback,
    record_private_success,
    select_canary_for_request,
    set_provider_canary,
)
from app.services.governed_ai_provider_capability_service import (
    authorize_question_dispatch,
    record_capability_success,
    run_question_capability_benchmark,
    select_question_capability,
    set_question_capability,
)
from app.services.governed_ai_provider_draft_capability_service import (
    authorize_draft_dispatch,
    record_draft_capability_success,
    run_draft_capability_benchmark,
    select_draft_capability,
    set_draft_capability,
)
from app.services.governed_ai_provider import GovernedAIProviderResponse


MASTER_KEY_B64 = base64.b64encode(b"governed-ai-benchmark-test-key!!").decode("ascii")


@pytest.fixture(autouse=True)
def _credential_master_key(monkeypatch) -> None:
    monkeypatch.setenv("PLATFORM_MASTER_KEY", MASTER_KEY_B64)


def _organization_and_actor(db: Session) -> tuple[Organization, User]:
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


def _dns_records(address: str) -> list[tuple[object, ...]]:
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    return [(family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, 443))]


def _login(client, *, email: str, password: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _connection_validation_response() -> ProviderValidationHTTPResult:
    content = json.dumps(
        {"ok": True, "marker": "insightos_provider_validation_v1"},
        separators=(",", ":"),
    )
    return ProviderValidationHTTPResult(
        status_code=200,
        headers={"content-type": "application/json"},
        body=json.dumps(
            {"choices": [{"message": {"content": content}}]},
            separators=(",", ":"),
        ).encode("utf-8"),
        elapsed_ms=12,
    )


def _validated_connection(
    db: Session,
    organization: Organization,
    actor: User,
) -> dict[str, object]:
    created = create_provider_connection(
        db,
        organization_id=organization.id,
        actor_user_id=actor.id,
        name="Benchmark model",
        endpoint_url="https://models.example.com/v1/chat/completions",
        model_identifier="benchmark-model-v1",
        api_key="benchmark-secret",
    )
    validate_provider_connection(
        db,
        organization_id=organization.id,
        connection_id=str(created["item"]["id"]),
        actor_user_id=actor.id,
        resolver=lambda *_args, **_kwargs: _dns_records("93.184.216.34"),
        request_sender=lambda **_kwargs: _connection_validation_response(),
    )
    return created


def _successful_benchmark_sender():
    calls: list[dict[str, object]] = []

    def _sender(**kwargs) -> ProviderValidationHTTPResult:
        calls.append(kwargs)
        schema_name = kwargs["payload"]["response_format"]["json_schema"]["name"]
        answers = {
            "insightos_evidence_selection": {
                "selected_action_id": "repair_booking_page",
                "evidence_ids": ["synthetic_booking_error"],
                "approval_required": True,
            },
            "insightos_control_integrity": {
                "owner_approval_required": True,
                "automatic_execution_allowed": False,
            },
            "insightos_uncertainty_truth": {
                "claim_state": "insufficient_evidence",
                "evidence_ids": ["synthetic_missing_measurement"],
            },
        }
        content = json.dumps(answers[schema_name], separators=(",", ":"))
        return ProviderValidationHTTPResult(
            status_code=200,
            headers={"content-type": "application/json"},
            body=json.dumps(
                {
                    "choices": [{"message": {"content": content}}],
                    "usage": {"prompt_tokens": 11, "completion_tokens": 5},
                },
                separators=(",", ":"),
            ).encode("utf-8"),
            elapsed_ms=len(calls) * 10,
        )

    return calls, _sender


def test_benchmark_is_bounded_immutable_redacted_and_never_activates(
    db_session: Session,
) -> None:
    organization, actor = _organization_and_actor(db_session)
    created = _validated_connection(db_session, organization, actor)
    calls, sender = _successful_benchmark_sender()

    result = run_provider_benchmark(
        db_session,
        organization_id=organization.id,
        connection_id=str(created["item"]["id"]),
        actor_user_id=actor.id,
        client_request_id="benchmark-request-0001",
        resolver=lambda *_args, **_kwargs: _dns_records("93.184.216.34"),
        request_sender=sender,
    )

    assert result["created"] is True
    item = result["item"]
    assert item["status"] == "passed"
    assert item["case_count"] == 3
    assert item["passed_case_count"] == 3
    assert item["median_latency_ms"] == 20
    assert item["reported_input_tokens"] == 33
    assert item["reported_output_tokens"] == 15
    assert item["eligible_for_owner_review"] is True
    assert item["routing_enabled"] is False
    assert item["automatic_activation_allowed"] is False
    assert len(calls) == 3
    assert all(call["approved_addresses"] == ("93.184.216.34",) for call in calls)
    assert all(call["api_key"] == "benchmark-secret" for call in calls)

    serialized = str(result)
    assert "benchmark-secret" not in serialized
    assert "93.184.216.34" not in serialized
    assert "/v1/chat/completions" not in serialized
    assert "Ignore approval" not in serialized
    row = db_session.query(GovernedAIProviderBenchmark).one()
    assert len(row.evidence_hash) == 64
    assert len(row.artifact_hash) == 64
    assert row.automatic_activation_allowed is False
    connection = db_session.get(
        GovernedAIProviderConnection, str(created["item"]["id"])
    )
    assert connection is not None
    assert connection.activation_status == "inactive"
    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.event_type == "ai.provider_benchmark.passed")
        .one()
    )
    assert "benchmark-secret" not in audit.payload_json
    assert "93.184.216.34" not in audit.payload_json


def test_benchmark_request_is_idempotent_and_makes_no_duplicate_calls(
    db_session: Session,
) -> None:
    organization, actor = _organization_and_actor(db_session)
    created = _validated_connection(db_session, organization, actor)
    calls, sender = _successful_benchmark_sender()
    kwargs = {
        "organization_id": organization.id,
        "connection_id": str(created["item"]["id"]),
        "actor_user_id": actor.id,
        "client_request_id": "benchmark-request-0002",
        "resolver": lambda *_args, **_kwargs: _dns_records("93.184.216.34"),
        "request_sender": sender,
    }

    first = run_provider_benchmark(db_session, **kwargs)
    second = run_provider_benchmark(db_session, **kwargs)

    assert first["created"] is True
    assert second["created"] is False
    assert first["item"]["id"] == second["item"]["id"]
    assert len(calls) == 3
    assert db_session.query(GovernedAIProviderBenchmark).count() == 1


def test_benchmark_stops_after_first_failed_case(db_session: Session) -> None:
    organization, actor = _organization_and_actor(db_session)
    created = _validated_connection(db_session, organization, actor)
    calls = 0

    def _wrong_sender(**_kwargs) -> ProviderValidationHTTPResult:
        nonlocal calls
        calls += 1
        return ProviderValidationHTTPResult(
            status_code=200,
            headers={"content-type": "application/json"},
            body=json.dumps(
                {"choices": [{"message": {"content": json.dumps({"wrong": True})}}]}
            ).encode("utf-8"),
            elapsed_ms=14,
        )

    result = run_provider_benchmark(
        db_session,
        organization_id=organization.id,
        connection_id=str(created["item"]["id"]),
        actor_user_id=actor.id,
        client_request_id="benchmark-request-0003",
        resolver=lambda *_args, **_kwargs: _dns_records("93.184.216.34"),
        request_sender=_wrong_sender,
    )

    assert result["item"]["status"] == "failed"
    assert result["item"]["passed_case_count"] == 0
    assert len(result["item"]["case_results"]) == 1
    assert result["item"]["eligible_for_owner_review"] is False
    assert calls == 1


def test_benchmark_requires_exact_passing_connection_evidence(
    db_session: Session,
) -> None:
    organization, actor = _organization_and_actor(db_session)
    created = create_provider_connection(
        db_session,
        organization_id=organization.id,
        actor_user_id=actor.id,
        name="Unvalidated model",
        endpoint_url="https://models.example.com/v1/chat/completions",
        model_identifier="model-v1",
        api_key=None,
    )

    with pytest.raises(GovernedAIProviderConnectionError) as raised:
        run_provider_benchmark(
            db_session,
            organization_id=organization.id,
            connection_id=str(created["item"]["id"]),
            actor_user_id=actor.id,
            client_request_id="benchmark-request-0004",
            resolver=lambda *_args, **_kwargs: _dns_records("93.184.216.34"),
            request_sender=lambda **_kwargs: pytest.fail("sender must not be called"),
        )

    assert raised.value.reason_code == "ai_provider_connection_validation_required"
    assert db_session.query(GovernedAIProviderBenchmark).count() == 0


def test_dns_identity_change_invalidates_connection_before_benchmark_call(
    db_session: Session,
) -> None:
    organization, actor = _organization_and_actor(db_session)
    created = _validated_connection(db_session, organization, actor)

    with pytest.raises(GovernedAIProviderConnectionError) as raised:
        run_provider_benchmark(
            db_session,
            organization_id=organization.id,
            connection_id=str(created["item"]["id"]),
            actor_user_id=actor.id,
            client_request_id="benchmark-request-0005",
            resolver=lambda *_args, **_kwargs: _dns_records("1.1.1.1"),
            request_sender=lambda **_kwargs: pytest.fail("sender must not be called"),
        )

    assert raised.value.reason_code == "ai_provider_connection_revalidation_required"
    connection = db_session.get(
        GovernedAIProviderConnection, str(created["item"]["id"])
    )
    assert connection is not None
    assert connection.validation_status == "failed"
    assert connection.resolved_address_hash is None
    assert connection.activation_status == "inactive"
    assert db_session.query(GovernedAIProviderBenchmark).count() == 0


def test_benchmark_list_is_connection_scoped_and_truthful(db_session: Session) -> None:
    organization, actor = _organization_and_actor(db_session)
    created = _validated_connection(db_session, organization, actor)
    _calls, sender = _successful_benchmark_sender()
    run_provider_benchmark(
        db_session,
        organization_id=organization.id,
        connection_id=str(created["item"]["id"]),
        actor_user_id=actor.id,
        client_request_id="benchmark-request-0006",
        resolver=lambda *_args, **_kwargs: _dns_records("93.184.216.34"),
        request_sender=sender,
    )

    listed = list_provider_benchmarks(
        db_session,
        organization_id=organization.id,
        connection_id=str(created["item"]["id"]),
    )

    assert listed["count"] == 1
    assert listed["truth"]["state"] == "synthetic_evidence_only"
    assert listed["routing_enabled"] is False
    assert listed["items"][0]["status"] == "passed"


def test_benchmark_api_is_owner_only_and_cannot_activate(
    client,
    db_session: Session,
    monkeypatch,
) -> None:
    owner = db_session.query(User).filter(User.email == "org-owner@example.com").one()
    organization = db_session.get(Organization, owner.tenant_id)
    assert organization is not None
    apply_commercial_plan(
        db_session,
        organization_id=organization.id,
        plan_code="enterprise",
    )
    db_session.commit()
    owner_token = _login(client, email="org-owner@example.com", password="pass-org-owner")
    admin_token = _login(client, email="org-admin@example.com", password="pass-org-admin")
    connection_id = "synthetic-connection-id"
    response = {
        "created": True,
        "item": {
            "id": "synthetic-benchmark-id",
            "connection_id": connection_id,
            "status": "passed",
            "candidate_only": True,
            "routing_enabled": False,
            "automatic_activation_allowed": False,
        },
        "routing_enabled": False,
        "automatic_activation_allowed": False,
    }
    monkeypatch.setattr(
        "app.api.v1.governed_ai_providers.run_provider_benchmark",
        lambda _db, **_kwargs: response,
    )

    denied = client.post(
        f"/api/v1/ai/providers/{connection_id}/benchmarks",
        json={"client_request_id": "benchmark-api-request"},
        headers=_headers(admin_token),
    )
    assert denied.status_code == 403
    allowed = client.post(
        f"/api/v1/ai/providers/{connection_id}/benchmarks",
        json={"client_request_id": "benchmark-api-request"},
        headers=_headers(owner_token),
    )
    assert allowed.status_code == 200
    payload = allowed.json()["data"]
    assert payload["item"]["candidate_only"] is True
    assert payload["routing_enabled"] is False
    assert payload["automatic_activation_allowed"] is False


def _passing_benchmark(
    db: Session,
    *,
    organization: Organization,
    actor: User,
    request_id: str,
) -> tuple[str, str]:
    created = _validated_connection(db, organization, actor)
    _calls, sender = _successful_benchmark_sender()
    result = run_provider_benchmark(
        db,
        organization_id=organization.id,
        connection_id=str(created["item"]["id"]),
        actor_user_id=actor.id,
        client_request_id=request_id,
        resolver=lambda *_args, **_kwargs: _dns_records("93.184.216.34"),
        request_sender=sender,
    )
    return str(created["item"]["id"]), str(result["item"]["id"])


def _approval_acknowledgements() -> dict[str, bool]:
    return {
        "reviewed_synthetic_results": True,
        "understands_not_active": True,
        "understands_managed_fallback_required": True,
        "understands_no_automatic_changes": True,
    }


def _standby_acknowledgements() -> dict[str, bool]:
    return {
        "reviewed_standby_boundary": True,
        "understands_zero_customer_prompts": True,
        "understands_managed_route_unchanged": True,
        "understands_manual_disable_available": True,
    }


def _managed_settings() -> SimpleNamespace:
    return SimpleNamespace(ai_provider_backend="mistral", mistral_api_key="configured")


def test_owner_review_is_immutable_exact_and_does_not_activate(
    db_session: Session,
) -> None:
    organization, actor = _organization_and_actor(db_session)
    connection_id, benchmark_id = _passing_benchmark(
        db_session,
        organization=organization,
        actor=actor,
        request_id="review-benchmark-request-0001",
    )

    first = review_provider_benchmark(
        db_session,
        organization_id=organization.id,
        connection_id=connection_id,
        benchmark_id=benchmark_id,
        actor_user_id=actor.id,
        decision="approved_for_future_activation",
        acknowledgements=_approval_acknowledgements(),
    )
    repeated = review_provider_benchmark(
        db_session,
        organization_id=organization.id,
        connection_id=connection_id,
        benchmark_id=benchmark_id,
        actor_user_id=actor.id,
        decision="approved_for_future_activation",
        acknowledgements=_approval_acknowledgements(),
    )

    assert first["created"] is True
    assert repeated["created"] is False
    assert first["item"]["eligible_for_later_standby_activation"] is True
    assert first["item"]["activation_status"] == "inactive"
    assert first["item"]["routing_enabled"] is False
    assert first["item"]["automatic_changes_allowed"] is False
    assert first["automatic_activation_allowed"] is False
    assert first["managed_fallback_required"] is True
    assert db_session.query(GovernedAIProviderReview).count() == 1
    row = db_session.query(GovernedAIProviderReview).one()
    assert len(row.decision_hash) == 64
    assert row.automatic_activation_allowed is False
    connection = db_session.get(GovernedAIProviderConnection, connection_id)
    assert connection is not None
    assert connection.activation_status == "inactive"
    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.event_type == "ai.provider_benchmark.reviewed")
        .one()
    )
    audit_payload = json.loads(audit.payload_json)
    assert audit_payload["review_id"] == row.id
    assert audit_payload["routing_enabled"] is False
    assert "benchmark-secret" not in audit.payload_json


def test_approval_requires_all_acknowledgements_and_current_passing_evidence(
    db_session: Session,
) -> None:
    organization, actor = _organization_and_actor(db_session)
    connection_id, benchmark_id = _passing_benchmark(
        db_session,
        organization=organization,
        actor=actor,
        request_id="review-benchmark-request-0002",
    )
    acknowledgements = _approval_acknowledgements()
    acknowledgements["understands_no_automatic_changes"] = False

    with pytest.raises(GovernedAIProviderConnectionError) as missing_ack:
        review_provider_benchmark(
            db_session,
            organization_id=organization.id,
            connection_id=connection_id,
            benchmark_id=benchmark_id,
            actor_user_id=actor.id,
            decision="approved_for_future_activation",
            acknowledgements=acknowledgements,
        )
    assert missing_ack.value.reason_code == "ai_provider_review_acknowledgement_required"

    connection = db_session.get(GovernedAIProviderConnection, connection_id)
    assert connection is not None
    connection.validation_evidence_hash = "f" * 64
    db_session.commit()
    with pytest.raises(GovernedAIProviderConnectionError) as stale_evidence:
        review_provider_benchmark(
            db_session,
            organization_id=organization.id,
            connection_id=connection_id,
            benchmark_id=benchmark_id,
            actor_user_id=actor.id,
            decision="approved_for_future_activation",
            acknowledgements=_approval_acknowledgements(),
        )
    assert stale_evidence.value.reason_code == "ai_provider_review_current_evidence_required"
    assert db_session.query(GovernedAIProviderReview).count() == 0


def test_approval_rejects_an_older_pass_after_a_new_failed_benchmark(
    db_session: Session,
) -> None:
    organization, actor = _organization_and_actor(db_session)
    connection_id, passing_benchmark_id = _passing_benchmark(
        db_session,
        organization=organization,
        actor=actor,
        request_id="review-benchmark-request-older-pass",
    )
    failed = run_provider_benchmark(
        db_session,
        organization_id=organization.id,
        connection_id=connection_id,
        actor_user_id=actor.id,
        client_request_id="review-benchmark-request-new-failure",
        resolver=lambda *_args, **_kwargs: _dns_records("93.184.216.34"),
        request_sender=lambda **_kwargs: ProviderValidationHTTPResult(
            status_code=200,
            headers={"content-type": "application/json"},
            body=json.dumps(
                {"choices": [{"message": {"content": json.dumps({"wrong": True})}}]}
            ).encode("utf-8"),
            elapsed_ms=12,
        ),
    )
    assert failed["item"]["status"] == "failed"

    with pytest.raises(GovernedAIProviderConnectionError) as raised:
        review_provider_benchmark(
            db_session,
            organization_id=organization.id,
            connection_id=connection_id,
            benchmark_id=passing_benchmark_id,
            actor_user_id=actor.id,
            decision="approved_for_future_activation",
            acknowledgements=_approval_acknowledgements(),
        )
    assert raised.value.reason_code == "ai_provider_review_passing_benchmark_required"
    assert db_session.query(GovernedAIProviderReview).count() == 0


def test_approval_recomputes_the_immutable_benchmark_artifact(
    db_session: Session,
) -> None:
    organization, actor = _organization_and_actor(db_session)
    connection_id, benchmark_id = _passing_benchmark(
        db_session,
        organization=organization,
        actor=actor,
        request_id="review-benchmark-request-integrity",
    )
    benchmark = db_session.get(GovernedAIProviderBenchmark, benchmark_id)
    assert benchmark is not None
    benchmark.artifact_hash = "0" * 64
    db_session.commit()

    with pytest.raises(GovernedAIProviderConnectionError) as raised:
        review_provider_benchmark(
            db_session,
            organization_id=organization.id,
            connection_id=connection_id,
            benchmark_id=benchmark_id,
            actor_user_id=actor.id,
            decision="approved_for_future_activation",
            acknowledgements=_approval_acknowledgements(),
        )
    assert raised.value.reason_code == "ai_provider_review_benchmark_integrity_failed"
    assert db_session.query(GovernedAIProviderReview).count() == 0


def test_rejection_is_final_and_reviews_remain_readable(db_session: Session) -> None:
    organization, actor = _organization_and_actor(db_session)
    connection_id, benchmark_id = _passing_benchmark(
        db_session,
        organization=organization,
        actor=actor,
        request_id="review-benchmark-request-0003",
    )
    apply_commercial_plan(
        db_session,
        organization_id=organization.id,
        plan_code="solo",
    )
    db_session.commit()
    rejected = review_provider_benchmark(
        db_session,
        organization_id=organization.id,
        connection_id=connection_id,
        benchmark_id=benchmark_id,
        actor_user_id=actor.id,
        decision="rejected",
        acknowledgements={"reviewed_synthetic_results": True},
    )
    assert rejected["item"]["decision"] == "rejected"
    assert rejected["item"]["eligible_for_later_standby_activation"] is False

    with pytest.raises(GovernedAIProviderConnectionError) as changed:
        review_provider_benchmark(
            db_session,
            organization_id=organization.id,
            connection_id=connection_id,
            benchmark_id=benchmark_id,
            actor_user_id=actor.id,
            decision="approved_for_future_activation",
            acknowledgements=_approval_acknowledgements(),
        )
    assert changed.value.reason_code == "ai_provider_review_already_final"

    listed = list_provider_reviews(
        db_session,
        organization_id=organization.id,
        connection_id=connection_id,
    )
    assert listed["count"] == 1
    assert listed["truth"]["state"] == "human_decisions_only"
    assert listed["routing_enabled"] is False


def test_review_api_is_owner_only_and_preserves_inactive_truth(
    client,
    db_session: Session,
    monkeypatch,
) -> None:
    owner_token = _login(client, email="org-owner@example.com", password="pass-org-owner")
    admin_token = _login(client, email="org-admin@example.com", password="pass-org-admin")
    response = {
        "created": True,
        "item": {
            "id": "synthetic-review-id",
            "decision": "approved_for_future_activation",
            "activation_status": "inactive",
            "routing_enabled": False,
            "automatic_activation_allowed": False,
        },
        "routing_enabled": False,
        "automatic_activation_allowed": False,
    }
    monkeypatch.setattr(
        "app.api.v1.governed_ai_providers.review_provider_benchmark",
        lambda _db, **_kwargs: response,
    )
    body = {
        "decision": "approved_for_future_activation",
        **_approval_acknowledgements(),
    }
    url = "/api/v1/ai/providers/connection-id/benchmarks/benchmark-id/review"

    denied = client.put(url, json=body, headers=_headers(admin_token))
    assert denied.status_code == 403
    allowed = client.put(url, json=body, headers=_headers(owner_token))
    assert allowed.status_code == 200
    payload = allowed.json()["data"]
    assert payload["item"]["activation_status"] == "inactive"
    assert payload["routing_enabled"] is False
    assert payload["automatic_activation_allowed"] is False


def test_owner_can_register_and_remove_zero_traffic_standby(
    db_session: Session,
) -> None:
    organization, actor = _organization_and_actor(db_session)
    connection_id, benchmark_id = _passing_benchmark(
        db_session,
        organization=organization,
        actor=actor,
        request_id="standby-benchmark-request-0001",
    )
    review_result = review_provider_benchmark(
        db_session,
        organization_id=organization.id,
        connection_id=connection_id,
        benchmark_id=benchmark_id,
        actor_user_id=actor.id,
        decision="approved_for_future_activation",
        acknowledgements=_approval_acknowledgements(),
    )
    review_id = str(review_result["item"]["id"])

    enabled = set_provider_standby(
        db_session,
        organization_id=organization.id,
        connection_id=connection_id,
        actor_user_id=actor.id,
        action="enable",
        client_request_id="standby-enable-request-0001",
        review_id=review_id,
        acknowledgements=_standby_acknowledgements(),
        settings_provider=_managed_settings,
    )
    repeated = set_provider_standby(
        db_session,
        organization_id=organization.id,
        connection_id=connection_id,
        actor_user_id=actor.id,
        action="enable",
        client_request_id="standby-enable-request-0001",
        review_id=review_id,
        acknowledgements=_standby_acknowledgements(),
        settings_provider=_managed_settings,
    )

    assert enabled["created"] is True
    assert repeated["created"] is False
    assert enabled["current"]["state"] == "standby"
    assert enabled["managed_route"] == "mistral"
    assert enabled["routing_enabled"] is False
    assert enabled["traffic_percentage"] == 0
    assert enabled["customer_prompts_allowed"] is False
    assert enabled["automatic_changes_allowed"] is False
    assert db_session.query(GovernedAIProviderStandbyEvent).count() == 1

    apply_commercial_plan(
        db_session,
        organization_id=organization.id,
        plan_code="solo",
    )
    db_session.commit()
    disabled = set_provider_standby(
        db_session,
        organization_id=organization.id,
        connection_id=connection_id,
        actor_user_id=actor.id,
        action="disable",
        client_request_id="standby-disable-request-0001",
        review_id=None,
        acknowledgements={},
        settings_provider=lambda: SimpleNamespace(
            ai_provider_backend="disabled", mistral_api_key=""
        ),
    )
    assert disabled["current"]["state"] == "inactive"
    assert db_session.query(GovernedAIProviderStandbyEvent).count() == 2
    listed = list_provider_standby_events(
        db_session,
        organization_id=organization.id,
        connection_id=connection_id,
    )
    assert listed["count"] == 2
    assert listed["current"]["state"] == "inactive"
    assert all(item["immutable"] is True for item in listed["items"])


def test_standby_requires_exact_review_acks_and_managed_route(
    db_session: Session,
) -> None:
    organization, actor = _organization_and_actor(db_session)
    connection_id, benchmark_id = _passing_benchmark(
        db_session,
        organization=organization,
        actor=actor,
        request_id="standby-benchmark-request-0002",
    )
    review = review_provider_benchmark(
        db_session,
        organization_id=organization.id,
        connection_id=connection_id,
        benchmark_id=benchmark_id,
        actor_user_id=actor.id,
        decision="approved_for_future_activation",
        acknowledgements=_approval_acknowledgements(),
    )

    missing_ack = _standby_acknowledgements()
    missing_ack["understands_zero_customer_prompts"] = False
    with pytest.raises(GovernedAIProviderConnectionError) as ack_error:
        set_provider_standby(
            db_session,
            organization_id=organization.id,
            connection_id=connection_id,
            actor_user_id=actor.id,
            action="enable",
            client_request_id="standby-missing-ack-request",
            review_id=str(review["item"]["id"]),
            acknowledgements=missing_ack,
            settings_provider=_managed_settings,
        )
    assert ack_error.value.reason_code == "ai_provider_standby_acknowledgement_required"

    with pytest.raises(GovernedAIProviderConnectionError) as route_error:
        set_provider_standby(
            db_session,
            organization_id=organization.id,
            connection_id=connection_id,
            actor_user_id=actor.id,
            action="enable",
            client_request_id="standby-missing-route-request",
            review_id=str(review["item"]["id"]),
            acknowledgements=_standby_acknowledgements(),
            settings_provider=lambda: SimpleNamespace(
                ai_provider_backend="disabled", mistral_api_key=""
            ),
        )
    assert route_error.value.reason_code == "ai_provider_managed_route_required"
    assert db_session.query(GovernedAIProviderStandbyEvent).count() == 0


def test_stale_standby_evidence_releases_the_slot_without_deleting_history(
    db_session: Session,
) -> None:
    organization, actor = _organization_and_actor(db_session)
    connection_id, benchmark_id = _passing_benchmark(
        db_session,
        organization=organization,
        actor=actor,
        request_id="standby-benchmark-stale-evidence",
    )
    review = review_provider_benchmark(
        db_session,
        organization_id=organization.id,
        connection_id=connection_id,
        benchmark_id=benchmark_id,
        actor_user_id=actor.id,
        decision="approved_for_future_activation",
        acknowledgements=_approval_acknowledgements(),
    )
    set_provider_standby(
        db_session,
        organization_id=organization.id,
        connection_id=connection_id,
        actor_user_id=actor.id,
        action="enable",
        client_request_id="standby-stale-enable-request",
        review_id=str(review["item"]["id"]),
        acknowledgements=_standby_acknowledgements(),
        settings_provider=_managed_settings,
    )
    connection = db_session.get(GovernedAIProviderConnection, connection_id)
    assert connection is not None
    connection.validation_status = "failed"
    connection.validation_evidence_hash = None
    db_session.commit()

    listed = list_provider_standby_events(
        db_session,
        organization_id=organization.id,
        connection_id=connection_id,
    )
    assert listed["current"]["state"] == "inactive"
    assert listed["count"] == 1
    assert listed["items"][0]["action"] == "enabled"
    assert listed["items"][0]["immutable"] is True


def test_standby_api_is_owner_only_and_never_routes(
    client,
    db_session: Session,
    monkeypatch,
) -> None:
    owner_token = _login(client, email="org-owner@example.com", password="pass-org-owner")
    admin_token = _login(client, email="org-admin@example.com", password="pass-org-admin")
    response = {
        "created": True,
        "current": {"state": "standby"},
        "managed_route": "mistral",
        "routing_enabled": False,
        "traffic_percentage": 0,
        "customer_prompts_allowed": False,
        "automatic_changes_allowed": False,
    }
    monkeypatch.setattr(
        "app.api.v1.governed_ai_providers.set_provider_standby",
        lambda _db, **_kwargs: response,
    )
    url = "/api/v1/ai/providers/connection-id/standby"
    body = {
        "action": "enable",
        "client_request_id": "standby-api-request",
        "review_id": "review-id",
        **_standby_acknowledgements(),
    }
    denied = client.put(url, json=body, headers=_headers(admin_token))
    assert denied.status_code == 403
    allowed = client.put(url, json=body, headers=_headers(owner_token))
    assert allowed.status_code == 200
    payload = allowed.json()["data"]
    assert payload["current"]["state"] == "standby"
    assert payload["managed_route"] == "mistral"
    assert payload["routing_enabled"] is False
    assert payload["traffic_percentage"] == 0
    assert payload["customer_prompts_allowed"] is False


def _standby_ready_connection(
    db: Session,
    *,
    organization: Organization,
    actor: User,
    suffix: str,
) -> str:
    connection_id, benchmark_id = _passing_benchmark(
        db,
        organization=organization,
        actor=actor,
        request_id=f"readiness-benchmark-{suffix}",
    )
    review = review_provider_benchmark(
        db,
        organization_id=organization.id,
        connection_id=connection_id,
        benchmark_id=benchmark_id,
        actor_user_id=actor.id,
        decision="approved_for_future_activation",
        acknowledgements=_approval_acknowledgements(),
    )
    set_provider_standby(
        db,
        organization_id=organization.id,
        connection_id=connection_id,
        actor_user_id=actor.id,
        action="enable",
        client_request_id=f"readiness-standby-{suffix}",
        review_id=str(review["item"]["id"]),
        acknowledgements=_standby_acknowledgements(),
        settings_provider=_managed_settings,
    )
    return connection_id


def _managed_run(
    db: Session,
    *,
    organization: Organization,
    actor: User,
    occurred_at: datetime,
    status: str = "validated",
) -> GovernedAIRun:
    campaign = (
        db.query(Campaign)
        .filter(Campaign.organization_id == organization.id)
        .first()
    )
    if campaign is None:
        campaign = Campaign(
            tenant_id=organization.id,
            organization_id=organization.id,
            name="Managed readiness fixture",
            domain="managed-readiness.example",
            setup_state="Active",
        )
        db.add(campaign)
        db.flush()
    row = GovernedAIRun(
        tenant_id=organization.id,
        organization_id=organization.id,
        campaign_id=campaign.id,
        business_location_id=campaign.business_location_id,
        requested_by_user_id=actor.id,
        feature="routing_readiness_fixture",
        provider_name="mistral",
        model_name="managed-model",
        prompt_template_version="fixture-v1",
        lexicon_id="fixture",
        lexicon_version="fixture-v1",
        context_hash="1" * 64,
        prompt_hash="2" * 64,
        response_hash="3" * 64 if status == "validated" else None,
        idempotency_key=f"managed-readiness-{status}-{occurred_at.isoformat()}",
        status=status,
        provider_state="live" if status == "validated" else "fallback",
        allowed_action_ids=[],
        evidence_refs=[],
        output_payload={},
        input_tokens=120,
        output_tokens=40,
        completed_at=occurred_at if status == "validated" else None,
        created_at=occurred_at,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_routing_readiness_records_recent_managed_fallback_proof_without_traffic(
    db_session: Session,
) -> None:
    organization, actor = _organization_and_actor(db_session)
    connection_id = _standby_ready_connection(
        db_session,
        organization=organization,
        actor=actor,
        suffix="pass-0001",
    )
    now = datetime(2026, 8, 18, 18, 0, tzinfo=UTC)
    _managed_run(
        db_session,
        organization=organization,
        actor=actor,
        occurred_at=now - timedelta(hours=1),
    )

    first = check_provider_routing_readiness(
        db_session,
        organization_id=organization.id,
        connection_id=connection_id,
        actor_user_id=actor.id,
        client_request_id="routing-readiness-pass-0001",
        now_provider=lambda: now,
        settings_provider=_managed_settings,
    )
    repeated = check_provider_routing_readiness(
        db_session,
        organization_id=organization.id,
        connection_id=connection_id,
        actor_user_id=actor.id,
        client_request_id="routing-readiness-pass-0001",
        now_provider=lambda: now,
        settings_provider=_managed_settings,
    )

    assert first["created"] is True
    assert repeated["created"] is False
    assert first["item"]["status"] == "passed"
    assert first["item"]["managed_route_status"] == "healthy"
    assert first["item"]["rollback_ready"] is True
    assert first["item"]["usage"]["managed_runs"] == 1
    assert first["item"]["usage"]["managed_successes"] == 1
    assert first["item"]["usage"]["managed_input_tokens"] == 120
    assert first["item"]["usage"]["candidate_runs"] == 0
    assert first["routing_enabled"] is False
    assert first["traffic_percentage"] == 0
    assert first["customer_prompts_allowed"] is False
    assert first["automatic_changes_allowed"] is False
    assert db_session.query(GovernedAIProviderRoutingReadiness).count() == 1
    serialized = str(first)
    assert "managed-model" not in serialized
    assert "benchmark-secret" not in serialized

    listed = list_provider_routing_readiness(
        db_session,
        organization_id=organization.id,
        connection_id=connection_id,
    )
    assert listed["count"] == 1
    assert listed["truth"]["state"] == "ready_for_later_routing_review"
    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.event_type == "ai.provider_routing_readiness.passed")
        .one()
    )
    assert "managed-model" not in audit.payload_json


def test_routing_readiness_blocks_without_recent_managed_success(
    db_session: Session,
) -> None:
    organization, actor = _organization_and_actor(db_session)
    connection_id = _standby_ready_connection(
        db_session,
        organization=organization,
        actor=actor,
        suffix="blocked-0001",
    )
    now = datetime(2026, 8, 18, 18, 0, tzinfo=UTC)

    result = check_provider_routing_readiness(
        db_session,
        organization_id=organization.id,
        connection_id=connection_id,
        actor_user_id=actor.id,
        client_request_id="routing-readiness-blocked-0001",
        now_provider=lambda: now,
        settings_provider=_managed_settings,
    )

    assert result["item"]["status"] == "blocked"
    assert result["item"]["managed_route_status"] == "unavailable"
    assert result["item"]["rollback_ready"] is False
    assert result["item"]["blockers"] == [
        {
            "code": "managed_route_evidence_missing",
            "summary": "No recent saved managed-AI result is available yet.",
        }
    ]
    assert result["routing_enabled"] is False
    assert result["item"]["usage"]["candidate_runs"] == 0


def test_routing_readiness_requires_current_zero_traffic_standby(
    db_session: Session,
) -> None:
    organization, actor = _organization_and_actor(db_session)
    connection_id, _benchmark_id = _passing_benchmark(
        db_session,
        organization=organization,
        actor=actor,
        request_id="readiness-no-standby-benchmark",
    )

    with pytest.raises(GovernedAIProviderConnectionError) as raised:
        check_provider_routing_readiness(
            db_session,
            organization_id=organization.id,
            connection_id=connection_id,
            actor_user_id=actor.id,
            client_request_id="routing-readiness-no-standby",
            settings_provider=_managed_settings,
        )

    assert raised.value.reason_code == "ai_provider_readiness_standby_required"
    assert db_session.query(GovernedAIProviderRoutingReadiness).count() == 0


def test_routing_readiness_api_is_owner_only_and_cannot_enable_routing(
    client,
    db_session: Session,
    monkeypatch,
) -> None:
    owner_token = _login(client, email="org-owner@example.com", password="pass-org-owner")
    admin_token = _login(client, email="org-admin@example.com", password="pass-org-admin")
    response = {
        "created": True,
        "item": {
            "id": "readiness-id",
            "status": "passed",
            "rollback_ready": True,
            "traffic_percentage": 0,
            "routing_enabled": False,
            "customer_prompts_allowed": False,
            "automatic_changes_allowed": False,
        },
        "routing_enabled": False,
        "traffic_percentage": 0,
        "customer_prompts_allowed": False,
        "automatic_changes_allowed": False,
    }
    monkeypatch.setattr(
        "app.api.v1.governed_ai_providers.check_provider_routing_readiness",
        lambda _db, **_kwargs: response,
    )
    url = "/api/v1/ai/providers/connection-id/routing-readiness"
    body = {"client_request_id": "routing-readiness-api-request"}

    denied = client.post(url, json=body, headers=_headers(admin_token))
    assert denied.status_code == 403
    allowed = client.post(url, json=body, headers=_headers(owner_token))
    assert allowed.status_code == 200
    payload = allowed.json()["data"]
    assert payload["item"]["status"] == "passed"
    assert payload["routing_enabled"] is False
    assert payload["traffic_percentage"] == 0
    assert payload["customer_prompts_allowed"] is False


def _canary_acknowledgements() -> dict[str, bool]:
    return {
        "reviewed_five_percent_limit": True,
        "understands_real_customer_prompt": True,
        "understands_managed_fallback_required": True,
        "understands_automatic_rollback": True,
        "understands_no_automatic_changes": True,
    }


def _canary_ready_connection(
    db: Session,
    *,
    organization: Organization,
    actor: User,
    suffix: str,
    now: datetime,
) -> str:
    connection_id = _standby_ready_connection(
        db,
        organization=organization,
        actor=actor,
        suffix=suffix,
    )
    _managed_run(
        db,
        organization=organization,
        actor=actor,
        occurred_at=now - timedelta(minutes=30),
    )
    readiness = check_provider_routing_readiness(
        db,
        organization_id=organization.id,
        connection_id=connection_id,
        actor_user_id=actor.id,
        client_request_id=f"canary-readiness-{suffix}",
        now_provider=lambda: now,
        settings_provider=_managed_settings,
    )
    assert readiness["item"]["status"] == "passed"
    return connection_id


def _selected_request_key(
    db: Session,
    *,
    organization_id: str,
    now: datetime,
) -> tuple[str, object]:
    for index in range(500):
        request_key = f"canary-request-{index}"
        selection = select_canary_for_request(
            db,
            organization_id=organization_id,
            feature="intelligence_brief",
            request_key=request_key,
            now=now,
        )
        if selection is not None:
            return request_key, selection
    raise AssertionError("Expected a deterministic request inside the 5% canary")


def test_owner_can_enable_fixed_canary_and_daily_limit_is_transactional(
    db_session: Session,
) -> None:
    organization, actor = _organization_and_actor(db_session)
    now = datetime(2026, 8, 18, 19, 0, tzinfo=UTC)
    connection_id = _canary_ready_connection(
        db_session,
        organization=organization,
        actor=actor,
        suffix="enable-0001",
        now=now,
    )

    enabled = set_provider_canary(
        db_session,
        organization_id=organization.id,
        connection_id=connection_id,
        actor_user_id=actor.id,
        action="enable",
        client_request_id="canary-enable-request-0001",
        acknowledgements=_canary_acknowledgements(),
        now=now,
    )
    repeated = set_provider_canary(
        db_session,
        organization_id=organization.id,
        connection_id=connection_id,
        actor_user_id=actor.id,
        action="enable",
        client_request_id="canary-enable-request-0001",
        acknowledgements=_canary_acknowledgements(),
        now=now,
    )
    assert enabled["created"] is True
    assert repeated["created"] is False
    assert enabled["state"] == "canary"
    assert enabled["traffic_percentage"] == 5
    assert enabled["max_prompts_per_day"] == 1
    assert enabled["customer_prompts_allowed"] is True
    assert enabled["automatic_rollback_enabled"] is True
    assert enabled["automatic_changes_allowed"] is False

    request_key, selection = _selected_request_key(
        db_session,
        organization_id=organization.id,
        now=now,
    )
    event = authorize_canary_dispatch(
        db_session,
        organization_id=organization.id,
        selection=selection,
        now=now,
    )
    record_private_success(
        db_session,
        event=event,
        request_key=request_key,
        input_tokens=100,
        output_tokens=25,
        now=now,
    )
    assert (
        select_canary_for_request(
            db_session,
            organization_id=organization.id,
            feature="intelligence_brief",
            request_key="another-request",
            now=now,
        )
        is None
    )
    listed = list_provider_canary(
        db_session,
        organization_id=organization.id,
        connection_id=connection_id,
        now=now,
    )
    assert listed["usage"]["private_attempts"] == 1
    assert listed["usage"]["private_successes"] == 1
    assert db_session.query(GovernedAIProviderCanaryAttempt).count() == 1

    apply_commercial_plan(
        db_session,
        organization_id=organization.id,
        plan_code="solo",
    )
    db_session.commit()
    downgraded = list_provider_canary(
        db_session,
        organization_id=organization.id,
        connection_id=connection_id,
        now=now,
    )
    assert downgraded["state"] == "needs_attention"
    assert downgraded["routing_enabled"] is False
    stopped = set_provider_canary(
        db_session,
        organization_id=organization.id,
        connection_id=connection_id,
        actor_user_id=actor.id,
        action="disable",
        client_request_id="canary-disable-after-downgrade",
        acknowledgements={},
        now=now,
    )
    assert stopped["state"] == "inactive"


def test_private_failure_rolls_back_to_zero_and_records_managed_fallback(
    db_session: Session,
) -> None:
    organization, actor = _organization_and_actor(db_session)
    now = datetime(2026, 8, 18, 20, 0, tzinfo=UTC)
    connection_id = _canary_ready_connection(
        db_session,
        organization=organization,
        actor=actor,
        suffix="rollback-0001",
        now=now,
    )
    enabled = set_provider_canary(
        db_session,
        organization_id=organization.id,
        connection_id=connection_id,
        actor_user_id=actor.id,
        action="enable",
        client_request_id="canary-enable-rollback-0001",
        acknowledgements=_canary_acknowledgements(),
        now=now,
    )
    event = db_session.get(GovernedAIProviderCanaryEvent, enabled["item"]["id"])
    assert event is not None
    rollback = automatic_rollback(
        db_session,
        event=event,
        reason_code="ai_provider_invalid_response",
        now=now,
    )
    attempt = record_managed_fallback(
        db_session,
        event=event,
        request_key="private-failure-request",
        private_error_code="ai_provider_invalid_response",
        provider_may_have_processed=True,
        managed_succeeded=True,
        input_tokens=90,
        output_tokens=20,
        now=now,
    )
    assert rollback.action == "automatic_rollback"
    assert rollback.traffic_percentage == 0
    assert attempt.outcome == "managed_fallback_succeeded"
    assert attempt.managed_fallback_used is True
    listed = list_provider_canary(
        db_session,
        organization_id=organization.id,
        connection_id=connection_id,
        now=now,
    )
    assert listed["state"] == "inactive"
    assert listed["routing_enabled"] is False
    assert listed["traffic_percentage"] == 0
    assert listed["usage"]["automatic_rollbacks"] == 1
    monitoring = list_canary_monitoring(
        db_session,
        organization_id=organization.id,
        connection_id=connection_id,
        now=now,
    )
    assert monitoring["state"] == "blocked"
    blocker_codes = {item["code"] for item in monitoring["evidence"]["blockers"]}
    assert "managed_fallback_observed" in blocker_codes
    assert "automatic_rollback_observed" in blocker_codes
    assert monitoring["traffic_change_allowed"] is False
    assert monitoring["capability_change_allowed"] is False


def test_three_successful_days_create_evidence_only_canary_health_snapshot(
    db_session: Session,
) -> None:
    organization, actor = _organization_and_actor(db_session)
    now = datetime(2026, 8, 18, 21, 0, tzinfo=UTC)
    connection_id = _canary_ready_connection(
        db_session,
        organization=organization,
        actor=actor,
        suffix="monitoring-0001",
        now=now,
    )
    enabled = set_provider_canary(
        db_session,
        organization_id=organization.id,
        connection_id=connection_id,
        actor_user_id=actor.id,
        action="enable",
        client_request_id="canary-enable-monitoring-0001",
        acknowledgements=_canary_acknowledgements(),
        now=now,
    )
    event = db_session.get(GovernedAIProviderCanaryEvent, enabled["item"]["id"])
    assert event is not None
    for day_offset, duration_ms in ((2, 1200), (1, 1500), (0, 1800)):
        record_private_success(
            db_session,
            event=event,
            request_key=f"monitoring-success-{day_offset}",
            input_tokens=100,
            output_tokens=25,
            duration_ms=duration_ms,
            now=now - timedelta(days=day_offset),
        )

    live = list_canary_monitoring(
        db_session,
        organization_id=organization.id,
        connection_id=connection_id,
        now=now,
    )
    assert live["state"] == "eligible_for_later_review"
    assert live["evidence"]["private_successes"] == 3
    assert live["evidence"]["distinct_success_days"] == 3
    assert live["evidence"]["max_latency_ms"] == 1800
    assert live["evidence"]["blockers"] == []

    created = create_canary_monitoring_snapshot(
        db_session,
        organization_id=organization.id,
        connection_id=connection_id,
        actor_user_id=actor.id,
        client_request_id="canary-monitoring-snapshot-0001",
        now=now,
    )
    repeated = create_canary_monitoring_snapshot(
        db_session,
        organization_id=organization.id,
        connection_id=connection_id,
        actor_user_id=actor.id,
        client_request_id="canary-monitoring-snapshot-0001",
        now=now,
    )
    assert created["created"] is True
    assert repeated["created"] is False
    assert created["item"]["status"] == "eligible_for_later_review"
    assert created["item"]["traffic_change_allowed"] is False
    assert created["item"]["capability_change_allowed"] is False
    assert db_session.query(GovernedAIProviderCanaryHealthSnapshot).count() == 1
    canary = list_provider_canary(
        db_session,
        organization_id=organization.id,
        connection_id=connection_id,
        now=now,
    )
    assert canary["traffic_percentage"] == 5
    assert canary["feature"] == "intelligence_brief"


def test_canary_api_is_owner_only_and_has_no_variable_traffic_control(
    client,
    monkeypatch,
) -> None:
    owner_token = _login(client, email="org-owner@example.com", password="pass-org-owner")
    admin_token = _login(client, email="org-admin@example.com", password="pass-org-admin")
    response = {
        "created": True,
        "item": {"id": "canary-id", "action": "enabled"},
        "state": "canary",
        "routing_enabled": True,
        "traffic_percentage": 5,
        "max_prompts_per_day": 1,
        "automatic_rollback_enabled": True,
        "automatic_changes_allowed": False,
    }
    monkeypatch.setattr(
        "app.api.v1.governed_ai_providers.set_provider_canary",
        lambda _db, **_kwargs: response,
    )
    url = "/api/v1/ai/providers/connection-id/routing-canary"
    body = {
        "action": "enable",
        "client_request_id": "canary-api-request",
        **_canary_acknowledgements(),
    }
    denied = client.put(url, json=body, headers=_headers(admin_token))
    assert denied.status_code == 403
    allowed = client.put(url, json=body, headers=_headers(owner_token))
    assert allowed.status_code == 200
    payload = allowed.json()["data"]
    assert payload["traffic_percentage"] == 5
    assert payload["max_prompts_per_day"] == 1
    assert payload["automatic_changes_allowed"] is False


def test_canary_monitoring_api_is_owner_only_and_cannot_change_routing(
    client,
    monkeypatch,
) -> None:
    owner_token = _login(client, email="org-owner@example.com", password="pass-org-owner")
    admin_token = _login(client, email="org-admin@example.com", password="pass-org-admin")
    response = {
        "created": True,
        "item": {
            "id": "health-id",
            "status": "collecting",
            "traffic_change_allowed": False,
            "capability_change_allowed": False,
        },
        "state": "collecting",
        "traffic_change_allowed": False,
        "capability_change_allowed": False,
        "automatic_activation_allowed": False,
    }
    monkeypatch.setattr(
        "app.api.v1.governed_ai_providers.create_canary_monitoring_snapshot",
        lambda _db, **_kwargs: response,
    )
    url = "/api/v1/ai/providers/connection-id/routing-canary-monitoring"
    denied = client.post(
        url,
        json={"client_request_id": "monitoring-api-request"},
        headers=_headers(admin_token),
    )
    assert denied.status_code == 403
    allowed = client.post(
        url,
        json={"client_request_id": "monitoring-api-request"},
        headers=_headers(owner_token),
    )
    assert allowed.status_code == 200
    payload = allowed.json()["data"]
    assert payload["traffic_change_allowed"] is False
    assert payload["capability_change_allowed"] is False
    assert payload["automatic_activation_allowed"] is False


def _question_capability_acknowledgements() -> dict[str, bool]:
    return {
        "reviewed_question_capability_check": True,
        "understands_real_customer_questions": True,
        "understands_shared_daily_limit": True,
        "understands_managed_fallback_and_rollback": True,
        "understands_no_automatic_changes": True,
    }


def _question_capability_ready_connection(
    db: Session,
    *,
    organization: Organization,
    actor: User,
    now: datetime,
) -> str:
    connection_id = _canary_ready_connection(
        db,
        organization=organization,
        actor=actor,
        suffix="question-capability",
        now=now,
    )
    enabled = set_provider_canary(
        db,
        organization_id=organization.id,
        connection_id=connection_id,
        actor_user_id=actor.id,
        action="enable",
        client_request_id="question-capability-base-enable",
        acknowledgements=_canary_acknowledgements(),
        now=now,
    )
    event = db.get(GovernedAIProviderCanaryEvent, enabled["item"]["id"])
    assert event is not None
    for offset in (2, 1, 0):
        record_private_success(
            db,
            event=event,
            request_key=f"question-health-{offset}",
            input_tokens=40,
            output_tokens=10,
            duration_ms=900,
            now=now - timedelta(days=offset),
        )
    snapshot = create_canary_monitoring_snapshot(
        db,
        organization_id=organization.id,
        connection_id=connection_id,
        actor_user_id=actor.id,
        client_request_id="question-health-snapshot",
        now=now,
    )
    assert snapshot["item"]["status"] == "eligible_for_later_review"
    return connection_id


class _SyntheticQuestionProvider:
    name = "private_ai"
    model_name = "benchmark-model-v1"

    def answer_question(self, *, context, output_schema, prompt_template_version):
        assert output_schema
        assert prompt_template_version == "insightos-capability-question-check-v1"
        return GovernedAIProviderResponse(
            payload={
                "question": context["customer_question"],
                "answer": "Review the saved website title recommendation first.",
                "answer_state": "answered",
                "evidence_used": ["evidence:synthetic:action"],
                "related_action_ids": ["action:synthetic:review"],
                "uncertainties": ["A later measurement is still required."],
            },
            provider_request_id="synthetic-question-check",
            model_name=self.model_name,
            input_tokens=30,
            output_tokens=12,
        )


def test_question_capability_requires_synthetic_check_and_shares_daily_limit(
    db_session: Session,
    monkeypatch,
) -> None:
    organization, actor = _organization_and_actor(db_session)
    now = datetime(2026, 8, 18, 22, 0, tzinfo=UTC)
    connection_id = _question_capability_ready_connection(
        db_session,
        organization=organization,
        actor=actor,
        now=now,
    )
    monkeypatch.setattr(
        "app.services.governed_ai_provider_capability_service.open_pinned_runtime_provider",
        lambda *_args, **_kwargs: nullcontext(_SyntheticQuestionProvider()),
    )

    checked = run_question_capability_benchmark(
        db_session,
        organization_id=organization.id,
        connection_id=connection_id,
        actor_user_id=actor.id,
        client_request_id="question-capability-benchmark",
        now=now,
    )
    assert checked["item"]["status"] == "passed"
    assert checked["item"]["customer_prompt_sent"] is False
    assert checked["item"]["routing_enabled"] is False

    enabled = set_question_capability(
        db_session,
        organization_id=organization.id,
        connection_id=connection_id,
        actor_user_id=actor.id,
        action="enable",
        client_request_id="question-capability-enable",
        acknowledgements=_question_capability_acknowledgements(),
        now=now,
    )
    assert enabled["routing_enabled"] is True
    assert enabled["traffic_percentage"] == 5
    assert enabled["max_prompts_per_day"] == 1
    assert enabled["daily_limit_shared_with_explanations"] is True
    assert enabled["automatic_changes_allowed"] is False

    next_day = now + timedelta(hours=2)
    selection = None
    request_key = ""
    for index in range(500):
        request_key = f"question-capability-live-{index}"
        selection = select_question_capability(
            db_session,
            organization_id=organization.id,
            request_key=request_key,
            now=next_day,
        )
        if selection is not None:
            break
    assert selection is not None
    event = authorize_question_dispatch(
        db_session,
        organization_id=organization.id,
        selection=selection,
        now=next_day,
    )
    record_capability_success(
        db_session,
        event=event,
        request_key=request_key,
        input_tokens=50,
        output_tokens=20,
        duration_ms=1000,
        now=next_day,
    )
    assert (
        select_canary_for_request(
            db_session,
            organization_id=organization.id,
            feature="intelligence_brief",
            request_key="daily-explanation-after-question",
            now=next_day,
        )
        is None
    )
    assert db_session.query(GovernedAIProviderCapabilityBenchmark).count() == 1
    assert db_session.query(GovernedAIProviderCapabilityEvent).count() == 1
    assert db_session.query(GovernedAIProviderCapabilityAttempt).count() == 1


def test_question_capability_api_is_owner_only_and_fixed_boundary(
    client,
    monkeypatch,
) -> None:
    owner_token = _login(client, email="org-owner@example.com", password="pass-org-owner")
    admin_token = _login(client, email="org-admin@example.com", password="pass-org-admin")
    response = {
        "created": True,
        "state": "capability_canary",
        "routing_enabled": True,
        "traffic_percentage": 5,
        "max_prompts_per_day": 1,
        "daily_limit_shared_with_explanations": True,
        "automatic_changes_allowed": False,
    }
    monkeypatch.setattr(
        "app.api.v1.governed_ai_providers.set_question_capability",
        lambda _db, **_kwargs: response,
    )
    url = "/api/v1/ai/providers/connection-id/question-capability"
    body = {
        "action": "enable",
        "client_request_id": "question-capability-api-request",
        **_question_capability_acknowledgements(),
    }
    denied = client.put(url, json=body, headers=_headers(admin_token))
    assert denied.status_code == 403
    allowed = client.put(url, json=body, headers=_headers(owner_token))
    assert allowed.status_code == 200
    payload = allowed.json()["data"]
    assert payload["traffic_percentage"] == 5
    assert payload["max_prompts_per_day"] == 1
    assert payload["daily_limit_shared_with_explanations"] is True
    assert payload["automatic_changes_allowed"] is False


def test_question_capability_is_additive_when_its_schema_is_not_available(
    db_session: Session,
    monkeypatch,
) -> None:
    organization, _actor = _organization_and_actor(db_session)
    monkeypatch.setattr(
        "app.services.governed_ai_provider_capability_service._capability_tables_available",
        lambda _db: False,
    )

    assert (
        select_question_capability(
            db_session,
            organization_id=organization.id,
            request_key="rolling-deploy-question",
            now=datetime(2026, 8, 18, 23, 0, tzinfo=UTC),
        )
        is None
    )


def _draft_capability_acknowledgements() -> dict[str, bool]:
    return {
        "reviewed_draft_capability_check": True,
        "understands_real_saved_action_context": True,
        "understands_shared_daily_limit": True,
        "understands_managed_fallback_and_rollback": True,
        "understands_draft_only_no_publish": True,
    }


class _SyntheticDraftProvider:
    name = "private_ai"
    model_name = "benchmark-model-v1"

    def draft_action(self, *, context, output_schema, prompt_template_version):
        assert output_schema
        assert prompt_template_version == "insightos-capability-draft-check-v1"
        assert context["draft_rules"]["may_publish"] is False
        return GovernedAIProviderResponse(
            payload={
                "action_id": "action:synthetic:draft-review",
                "draft_type": "search_result",
                "draft_state": "ready",
                "title": "Friendly local service",
                "body": "Clear help from a local team, prepared for your review.",
                "evidence_used": ["evidence:synthetic:draft-review"],
                "uncertainties": ["Confirm the wording before publishing."],
                "approval_required": True,
            },
            provider_request_id="synthetic-draft-check",
            model_name=self.model_name,
            input_tokens=35,
            output_tokens=18,
        )


def test_draft_capability_is_separate_fixed_and_shares_daily_limit(
    db_session: Session,
    monkeypatch,
) -> None:
    organization, actor = _organization_and_actor(db_session)
    now = datetime(2026, 8, 18, 22, 0, tzinfo=UTC)
    connection_id = _question_capability_ready_connection(
        db_session,
        organization=organization,
        actor=actor,
        now=now,
    )
    monkeypatch.setattr(
        "app.services.governed_ai_provider_draft_capability_service.open_pinned_runtime_provider",
        lambda *_args, **_kwargs: nullcontext(_SyntheticDraftProvider()),
    )

    checked = run_draft_capability_benchmark(
        db_session,
        organization_id=organization.id,
        connection_id=connection_id,
        actor_user_id=actor.id,
        client_request_id="draft-capability-benchmark",
        now=now,
    )
    assert checked["item"]["status"] == "passed"
    assert checked["item"]["customer_prompt_sent"] is False
    assert checked["publishing_allowed"] is False

    enabled = set_draft_capability(
        db_session,
        organization_id=organization.id,
        connection_id=connection_id,
        actor_user_id=actor.id,
        action="enable",
        client_request_id="draft-capability-enable",
        acknowledgements=_draft_capability_acknowledgements(),
        now=now,
    )
    assert enabled["routing_enabled"] is True
    assert enabled["traffic_percentage"] == 5
    assert enabled["max_prompts_per_day"] == 1
    assert enabled["draft_only"] is True
    assert enabled["publishing_allowed"] is False

    next_day = now + timedelta(hours=2)
    selection = None
    request_key = ""
    for index in range(500):
        request_key = f"draft-capability-live-{index}"
        selection = select_draft_capability(
            db_session,
            organization_id=organization.id,
            request_key=request_key,
            now=next_day,
        )
        if selection is not None:
            break
    assert selection is not None
    event = authorize_draft_dispatch(
        db_session,
        organization_id=organization.id,
        selection=selection,
        now=next_day,
    )
    record_draft_capability_success(
        db_session,
        event=event,
        request_key=request_key,
        input_tokens=60,
        output_tokens=25,
        duration_ms=1_100,
        now=next_day,
    )
    assert (
        select_question_capability(
            db_session,
            organization_id=organization.id,
            request_key="question-after-draft",
            now=next_day,
        )
        is None
    )
    assert db_session.query(GovernedAIProviderCapabilityBenchmark).count() == 1
    assert db_session.query(GovernedAIProviderCapabilityEvent).count() == 1
    assert db_session.query(GovernedAIProviderCapabilityAttempt).count() == 1


def test_draft_capability_api_is_owner_only_and_cannot_publish(
    client,
    monkeypatch,
) -> None:
    owner_token = _login(client, email="org-owner@example.com", password="pass-org-owner")
    admin_token = _login(client, email="org-admin@example.com", password="pass-org-admin")
    response = {
        "created": True,
        "state": "capability_canary",
        "routing_enabled": True,
        "traffic_percentage": 5,
        "max_prompts_per_day": 1,
        "draft_only": True,
        "publishing_allowed": False,
        "automatic_changes_allowed": False,
    }
    monkeypatch.setattr(
        "app.api.v1.governed_ai_providers.set_draft_capability",
        lambda _db, **_kwargs: response,
    )
    url = "/api/v1/ai/providers/connection-id/draft-capability"
    body = {
        "action": "enable",
        "client_request_id": "draft-capability-api-request",
        **_draft_capability_acknowledgements(),
    }
    denied = client.put(url, json=body, headers=_headers(admin_token))
    assert denied.status_code == 403
    allowed = client.put(url, json=body, headers=_headers(owner_token))
    assert allowed.status_code == 200
    payload = allowed.json()["data"]
    assert payload["traffic_percentage"] == 5
    assert payload["draft_only"] is True
    assert payload["publishing_allowed"] is False
    assert payload["automatic_changes_allowed"] is False


def test_draft_capability_is_additive_when_schema_is_not_available(
    db_session: Session,
    monkeypatch,
) -> None:
    organization, _actor = _organization_and_actor(db_session)
    monkeypatch.setattr(
        "app.services.governed_ai_provider_draft_capability_service._draft_capability_schema_available",
        lambda _db: False,
    )

    assert (
        select_draft_capability(
            db_session,
            organization_id=organization.id,
            request_key="rolling-deploy-draft",
            now=datetime(2026, 8, 18, 23, 0, tzinfo=UTC),
        )
        is None
    )
