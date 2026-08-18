from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.db.session import set_session_security_context
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
from app.models.user import User


pytestmark = pytest.mark.postgres_required


def _connection(db: Session, *, user: User, suffix: str) -> GovernedAIProviderConnection:
    now = datetime.now(UTC)
    row = GovernedAIProviderConnection(
        tenant_id=str(user.tenant_id),
        organization_id=str(user.tenant_id),
        name=f"Security model {suffix}",
        adapter_type="openai_compatible",
        status="candidate",
        endpoint_host=f"{suffix}.example.com",
        model_identifier=f"model-{suffix}",
        capabilities_json=json.dumps(["explain"]),
        credential_configured=False,
        validation_status="passed",
        network_validation_status="passed",
        last_validation_reason="ai_provider_connection_validated",
        resolved_address_hash=suffix[0] * 64,
        last_validation_latency_ms=10,
        validation_schema_version="openai-compatible-connection-v1",
        validation_evidence_hash=suffix[-1] * 64,
        activation_status="inactive",
        automatic_activation_allowed=False,
        created_by_user_id=user.id,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    return row


def _benchmark(
    db: Session,
    *,
    user: User,
    connection: GovernedAIProviderConnection,
    suffix: str,
) -> GovernedAIProviderBenchmark:
    row = GovernedAIProviderBenchmark(
        tenant_id=str(user.tenant_id),
        organization_id=str(user.tenant_id),
        connection_id=connection.id,
        benchmark_version="governed-provider-quality-v1",
        connection_evidence_hash=str(connection.validation_evidence_hash),
        status="passed",
        case_count=3,
        passed_case_count=3,
        median_latency_ms=10,
        reported_input_tokens=0,
        reported_output_tokens=0,
        case_results=[],
        evidence_hash="e" * 64,
        artifact_hash=suffix[0] * 64,
        idempotency_key=f"security-benchmark-{suffix}",
        automatic_activation_allowed=False,
        created_by_user_id=user.id,
        created_at=datetime.now(UTC),
    )
    db.add(row)
    db.flush()
    return row


def _review(
    db: Session,
    *,
    user: User,
    connection: GovernedAIProviderConnection,
    benchmark: GovernedAIProviderBenchmark,
    suffix: str,
) -> GovernedAIProviderReview:
    row = GovernedAIProviderReview(
        tenant_id=str(user.tenant_id),
        organization_id=str(user.tenant_id),
        connection_id=connection.id,
        benchmark_id=benchmark.id,
        decision="approved_for_future_activation",
        benchmark_artifact_hash=benchmark.artifact_hash,
        connection_evidence_hash=benchmark.connection_evidence_hash,
        acknowledgements={
            "reviewed_synthetic_results": True,
            "understands_not_active": True,
            "understands_managed_fallback_required": True,
            "understands_no_automatic_changes": True,
        },
        decision_hash=suffix[0] * 64,
        automatic_activation_allowed=False,
        reviewed_by_user_id=user.id,
        reviewed_at=datetime.now(UTC),
    )
    db.add(row)
    db.flush()
    return row


def test_provider_benchmarks_are_rls_scoped_and_immutable(
    db_session: Session,
) -> None:
    user_a = db_session.query(User).filter(User.email == "a@example.com").one()
    user_b = db_session.query(User).filter(User.email == "b@example.com").one()
    connection_a = _connection(db_session, user=user_a, suffix="alpha")
    connection_b = _connection(db_session, user=user_b, suffix="bravo")
    benchmark_a = _benchmark(
        db_session,
        user=user_a,
        connection=connection_a,
        suffix="alpha",
    )
    benchmark_b = _benchmark(
        db_session,
        user=user_b,
        connection=connection_b,
        suffix="bravo",
    )
    db_session.commit()

    isolated = Session(bind=db_session.get_bind(), autoflush=False, autocommit=False)
    try:
        set_session_security_context(
            isolated,
            tenant_id=str(user_a.tenant_id),
            organization_id=str(user_a.tenant_id),
            user_id=user_a.id,
            platform_access=False,
        )
        visible = set(
            isolated.execute(
                select(GovernedAIProviderBenchmark.id).where(
                    GovernedAIProviderBenchmark.id.in_(
                        [benchmark_a.id, benchmark_b.id]
                    )
                )
            ).scalars()
        )
        assert visible == {benchmark_a.id}
    finally:
        isolated.rollback()
        isolated.close()

    update_session = Session(
        bind=db_session.get_bind(), autoflush=False, autocommit=False
    )
    try:
        set_session_security_context(
            update_session,
            tenant_id=str(user_a.tenant_id),
            organization_id=str(user_a.tenant_id),
            user_id=user_a.id,
            platform_access=False,
        )
        with pytest.raises(DBAPIError):
            update_session.execute(
                update(GovernedAIProviderBenchmark)
                .where(GovernedAIProviderBenchmark.id == benchmark_a.id)
                .values(status="failed")
            )
            update_session.flush()
    finally:
        update_session.rollback()
        update_session.close()

    delete_session = Session(
        bind=db_session.get_bind(), autoflush=False, autocommit=False
    )
    try:
        set_session_security_context(
            delete_session,
            tenant_id=str(user_a.tenant_id),
            organization_id=str(user_a.tenant_id),
            user_id=user_a.id,
            platform_access=False,
        )
        with pytest.raises(DBAPIError):
            delete_session.execute(
                delete(GovernedAIProviderBenchmark).where(
                    GovernedAIProviderBenchmark.id == benchmark_a.id
                )
            )
            delete_session.flush()
    finally:
        delete_session.rollback()
        delete_session.close()


def test_provider_reviews_are_rls_scoped_and_immutable(db_session: Session) -> None:
    user_a = db_session.query(User).filter(User.email == "a@example.com").one()
    user_b = db_session.query(User).filter(User.email == "b@example.com").one()
    connection_a = _connection(db_session, user=user_a, suffix="alpha-review")
    connection_b = _connection(db_session, user=user_b, suffix="bravo-review")
    benchmark_a = _benchmark(
        db_session,
        user=user_a,
        connection=connection_a,
        suffix="alpha-review",
    )
    benchmark_b = _benchmark(
        db_session,
        user=user_b,
        connection=connection_b,
        suffix="bravo-review",
    )
    review_a = _review(
        db_session,
        user=user_a,
        connection=connection_a,
        benchmark=benchmark_a,
        suffix="alpha-review",
    )
    review_b = _review(
        db_session,
        user=user_b,
        connection=connection_b,
        benchmark=benchmark_b,
        suffix="bravo-review",
    )
    db_session.commit()

    isolated = Session(bind=db_session.get_bind(), autoflush=False, autocommit=False)
    try:
        set_session_security_context(
            isolated,
            tenant_id=str(user_a.tenant_id),
            organization_id=str(user_a.tenant_id),
            user_id=user_a.id,
            platform_access=False,
        )
        visible = set(
            isolated.execute(
                select(GovernedAIProviderReview.id).where(
                    GovernedAIProviderReview.id.in_([review_a.id, review_b.id])
                )
            ).scalars()
        )
        assert visible == {review_a.id}
    finally:
        isolated.rollback()
        isolated.close()

    update_session = Session(
        bind=db_session.get_bind(), autoflush=False, autocommit=False
    )
    try:
        set_session_security_context(
            update_session,
            tenant_id=str(user_a.tenant_id),
            organization_id=str(user_a.tenant_id),
            user_id=user_a.id,
            platform_access=False,
        )
        with pytest.raises(DBAPIError):
            update_session.execute(
                update(GovernedAIProviderReview)
                .where(GovernedAIProviderReview.id == review_a.id)
                .values(decision="rejected")
            )
            update_session.flush()
    finally:
        update_session.rollback()
        update_session.close()

    delete_session = Session(
        bind=db_session.get_bind(), autoflush=False, autocommit=False
    )
    try:
        set_session_security_context(
            delete_session,
            tenant_id=str(user_a.tenant_id),
            organization_id=str(user_a.tenant_id),
            user_id=user_a.id,
            platform_access=False,
        )
        with pytest.raises(DBAPIError):
            delete_session.execute(
                delete(GovernedAIProviderReview).where(
                    GovernedAIProviderReview.id == review_a.id
                )
            )
            delete_session.flush()
    finally:
        delete_session.rollback()
        delete_session.close()


def test_provider_standby_events_are_rls_scoped_and_immutable(
    db_session: Session,
) -> None:
    user_a = db_session.query(User).filter(User.email == "a@example.com").one()
    user_b = db_session.query(User).filter(User.email == "b@example.com").one()
    rows: list[GovernedAIProviderStandbyEvent] = []
    for user, suffix in ((user_a, "alpha-standby"), (user_b, "bravo-standby")):
        connection = _connection(db_session, user=user, suffix=suffix)
        benchmark = _benchmark(
            db_session, user=user, connection=connection, suffix=suffix
        )
        review = _review(
            db_session,
            user=user,
            connection=connection,
            benchmark=benchmark,
            suffix=suffix,
        )
        row = GovernedAIProviderStandbyEvent(
            tenant_id=str(user.tenant_id),
            organization_id=str(user.tenant_id),
            connection_id=connection.id,
            benchmark_id=benchmark.id,
            review_id=review.id,
            action="enabled",
            managed_backend="mistral",
            routing_mode="zero_traffic_standby",
            traffic_percentage=0,
            customer_prompts_allowed=False,
            automatic_changes_allowed=False,
            automatic_activation_allowed=False,
            benchmark_artifact_hash=benchmark.artifact_hash,
            connection_evidence_hash=benchmark.connection_evidence_hash,
            review_decision_hash=review.decision_hash,
            acknowledgements={},
            artifact_hash=suffix[0] * 64,
            idempotency_key=f"security-standby-{suffix}",
            created_by_user_id=user.id,
            created_at=datetime.now(UTC),
        )
        db_session.add(row)
        rows.append(row)
    db_session.commit()

    isolated = Session(bind=db_session.get_bind(), autoflush=False, autocommit=False)
    try:
        set_session_security_context(
            isolated,
            tenant_id=str(user_a.tenant_id),
            organization_id=str(user_a.tenant_id),
            user_id=user_a.id,
            platform_access=False,
        )
        visible = set(
            isolated.execute(
                select(GovernedAIProviderStandbyEvent.id).where(
                    GovernedAIProviderStandbyEvent.id.in_([row.id for row in rows])
                )
            ).scalars()
        )
        assert visible == {rows[0].id}
    finally:
        isolated.rollback()
        isolated.close()

    mutation_session = Session(
        bind=db_session.get_bind(), autoflush=False, autocommit=False
    )
    try:
        set_session_security_context(
            mutation_session,
            tenant_id=str(user_a.tenant_id),
            organization_id=str(user_a.tenant_id),
            user_id=user_a.id,
            platform_access=False,
        )
        with pytest.raises(DBAPIError):
            mutation_session.execute(
                update(GovernedAIProviderStandbyEvent)
                .where(GovernedAIProviderStandbyEvent.id == rows[0].id)
                .values(action="disabled")
            )
            mutation_session.flush()
    finally:
        mutation_session.rollback()
        mutation_session.close()


def test_provider_readiness_is_rls_scoped_immutable_and_zero_traffic(
    db_session: Session,
) -> None:
    user_a = db_session.query(User).filter(User.email == "a@example.com").one()
    user_b = db_session.query(User).filter(User.email == "b@example.com").one()
    readiness_rows: list[GovernedAIProviderRoutingReadiness] = []
    canary_events: list[GovernedAIProviderCanaryEvent] = []
    canary_attempts: list[GovernedAIProviderCanaryAttempt] = []
    canary_health_rows: list[GovernedAIProviderCanaryHealthSnapshot] = []
    capability_benchmarks: list[GovernedAIProviderCapabilityBenchmark] = []
    capability_events: list[GovernedAIProviderCapabilityEvent] = []
    capability_attempts: list[GovernedAIProviderCapabilityAttempt] = []
    for user, suffix in ((user_a, "alpha-ready"), (user_b, "bravo-ready")):
        connection = _connection(db_session, user=user, suffix=suffix)
        benchmark = _benchmark(
            db_session, user=user, connection=connection, suffix=suffix
        )
        review = _review(
            db_session,
            user=user,
            connection=connection,
            benchmark=benchmark,
            suffix=suffix,
        )
        standby = GovernedAIProviderStandbyEvent(
            tenant_id=str(user.tenant_id),
            organization_id=str(user.tenant_id),
            connection_id=connection.id,
            benchmark_id=benchmark.id,
            review_id=review.id,
            action="enabled",
            managed_backend="mistral",
            routing_mode="zero_traffic_standby",
            traffic_percentage=0,
            customer_prompts_allowed=False,
            automatic_changes_allowed=False,
            automatic_activation_allowed=False,
            benchmark_artifact_hash=benchmark.artifact_hash,
            connection_evidence_hash=benchmark.connection_evidence_hash,
            review_decision_hash=review.decision_hash,
            acknowledgements={},
            artifact_hash=suffix[0] * 64,
            idempotency_key=f"security-ready-standby-{suffix}",
            created_by_user_id=user.id,
            created_at=datetime.now(UTC),
        )
        db_session.add(standby)
        db_session.flush()
        readiness = GovernedAIProviderRoutingReadiness(
            tenant_id=str(user.tenant_id),
            organization_id=str(user.tenant_id),
            connection_id=connection.id,
            standby_event_id=standby.id,
            readiness_version="managed-fallback-readiness-v1",
            status="passed",
            managed_backend="mistral",
            managed_route_status="healthy",
            managed_evidence_hash="a" * 64,
            managed_evidence_at=datetime.now(UTC),
            standby_evidence_current=True,
            rollback_ready=True,
            blockers=[],
            usage_window_days=30,
            managed_run_count=1,
            managed_validated_count=1,
            managed_fallback_count=0,
            managed_input_tokens=5,
            managed_output_tokens=2,
            candidate_run_count=0,
            traffic_percentage=0,
            routing_enabled=False,
            customer_prompts_allowed=False,
            automatic_changes_allowed=False,
            automatic_activation_allowed=False,
            artifact_hash=suffix[-1] * 64,
            idempotency_key=f"security-readiness-{suffix}",
            created_by_user_id=user.id,
            created_at=datetime.now(UTC),
        )
        db_session.add(readiness)
        db_session.flush()
        readiness_rows.append(readiness)
        canary = GovernedAIProviderCanaryEvent(
            tenant_id=str(user.tenant_id),
            organization_id=str(user.tenant_id),
            connection_id=connection.id,
            readiness_id=readiness.id,
            action="enabled",
            state="canary",
            feature="intelligence_brief",
            traffic_percentage=5,
            max_prompts_per_day=1,
            customer_prompts_allowed=True,
            automatic_rollback_enabled=True,
            automatic_changes_allowed=False,
            automatic_activation_allowed=False,
            readiness_artifact_hash=readiness.artifact_hash,
            acknowledgements={},
            reason_code="ai_provider_canary_owner_enabled",
            artifact_hash=suffix[2] * 64,
            idempotency_key=f"security-canary-{suffix}",
            created_by_user_id=user.id,
            created_at=datetime.now(UTC),
        )
        db_session.add(canary)
        db_session.flush()
        attempt = GovernedAIProviderCanaryAttempt(
            tenant_id=str(user.tenant_id),
            organization_id=str(user.tenant_id),
            connection_id=connection.id,
            canary_event_id=canary.id,
            feature="intelligence_brief",
            outcome="private_succeeded",
            request_key_hash=suffix[3] * 64,
            customer_prompt_sent=True,
            provider_may_have_processed=True,
            managed_fallback_used=False,
            automatic_rollback_triggered=False,
            automatic_changes_allowed=False,
            input_tokens=3,
            output_tokens=1,
            duration_ms=1000,
            cost_owner="customer",
            platform_provider_cost=0,
            artifact_hash=suffix[4] * 64,
            created_at=datetime.now(UTC),
        )
        db_session.add(attempt)
        health = GovernedAIProviderCanaryHealthSnapshot(
            tenant_id=str(user.tenant_id),
            organization_id=str(user.tenant_id),
            connection_id=connection.id,
            canary_event_id=canary.id,
            feature="intelligence_brief",
            status="collecting",
            window_days=30,
            required_success_days=3,
            max_latency_threshold_ms=8000,
            private_successes=1,
            distinct_success_days=1,
            managed_fallbacks=0,
            automatic_rollbacks=0,
            max_latency_ms=1000,
            blockers=[{"code": "more_successful_days_required"}],
            traffic_change_allowed=False,
            capability_change_allowed=False,
            automatic_activation_allowed=False,
            automatic_changes_allowed=False,
            artifact_hash=suffix[5] * 64,
            idempotency_key=f"security-canary-health-{suffix}",
            created_by_user_id=user.id,
            created_at=datetime.now(UTC),
        )
        db_session.add(health)
        db_session.flush()
        capability_benchmark = GovernedAIProviderCapabilityBenchmark(
            tenant_id=str(user.tenant_id),
            organization_id=str(user.tenant_id),
            connection_id=connection.id,
            health_snapshot_id=health.id,
            capability="intelligence_question",
            schema_version="governed-evidence-answer-v1",
            status="passed",
            reason_code="ai_provider_question_capability_passed",
            case_count=1,
            latency_ms=500,
            input_tokens=10,
            output_tokens=5,
            customer_prompt_sent=False,
            routing_enabled=False,
            automatic_activation_allowed=False,
            automatic_changes_allowed=False,
            health_artifact_hash=health.artifact_hash,
            connection_evidence_hash=str(connection.validation_evidence_hash),
            artifact_hash=suffix[6] * 64,
            idempotency_key=f"security-question-benchmark-{suffix}",
            created_by_user_id=user.id,
            created_at=datetime.now(UTC),
        )
        db_session.add(capability_benchmark)
        db_session.flush()
        capability_event = GovernedAIProviderCapabilityEvent(
            tenant_id=str(user.tenant_id),
            organization_id=str(user.tenant_id),
            connection_id=connection.id,
            health_snapshot_id=health.id,
            benchmark_id=capability_benchmark.id,
            action="enabled",
            state="capability_canary",
            capability="intelligence_question",
            traffic_percentage=5,
            max_prompts_per_day=1,
            customer_prompts_allowed=True,
            automatic_rollback_enabled=True,
            automatic_activation_allowed=False,
            automatic_changes_allowed=False,
            acknowledgements={},
            reason_code="ai_provider_question_capability_owner_enabled",
            artifact_hash=suffix[7] * 64,
            idempotency_key=f"security-question-event-{suffix}",
            created_by_user_id=user.id,
            created_at=datetime.now(UTC),
        )
        db_session.add(capability_event)
        db_session.flush()
        capability_attempt = GovernedAIProviderCapabilityAttempt(
            tenant_id=str(user.tenant_id),
            organization_id=str(user.tenant_id),
            connection_id=connection.id,
            capability_event_id=capability_event.id,
            capability="intelligence_question",
            outcome="private_succeeded",
            request_key_hash=suffix[8] * 64,
            customer_prompt_sent=True,
            provider_may_have_processed=True,
            managed_fallback_used=False,
            automatic_rollback_triggered=False,
            automatic_changes_allowed=False,
            input_tokens=3,
            output_tokens=1,
            duration_ms=600,
            cost_owner="customer",
            platform_provider_cost=0,
            artifact_hash=suffix[9] * 64,
            created_at=datetime.now(UTC),
        )
        db_session.add(capability_attempt)
        canary_events.append(canary)
        canary_attempts.append(attempt)
        canary_health_rows.append(health)
        capability_benchmarks.append(capability_benchmark)
        capability_events.append(capability_event)
        capability_attempts.append(capability_attempt)
    db_session.commit()

    isolated = Session(bind=db_session.get_bind(), autoflush=False, autocommit=False)
    try:
        set_session_security_context(
            isolated,
            tenant_id=str(user_a.tenant_id),
            organization_id=str(user_a.tenant_id),
            user_id=user_a.id,
            platform_access=False,
        )
        visible = set(
            isolated.execute(
                select(GovernedAIProviderRoutingReadiness.id).where(
                    GovernedAIProviderRoutingReadiness.id.in_(
                        [row.id for row in readiness_rows]
                    )
                )
            ).scalars()
        )
        assert visible == {readiness_rows[0].id}
        visible_canaries = set(
            isolated.execute(
                select(GovernedAIProviderCanaryEvent.id).where(
                    GovernedAIProviderCanaryEvent.id.in_(
                        [row.id for row in canary_events]
                    )
                )
            ).scalars()
        )
        visible_attempts = set(
            isolated.execute(
                select(GovernedAIProviderCanaryAttempt.id).where(
                    GovernedAIProviderCanaryAttempt.id.in_(
                        [row.id for row in canary_attempts]
                    )
                )
            ).scalars()
        )
        visible_health = set(
            isolated.execute(
                select(GovernedAIProviderCanaryHealthSnapshot.id).where(
                    GovernedAIProviderCanaryHealthSnapshot.id.in_(
                        [row.id for row in canary_health_rows]
                    )
                )
            ).scalars()
        )
        assert visible_canaries == {canary_events[0].id}
        assert visible_attempts == {canary_attempts[0].id}
        assert visible_health == {canary_health_rows[0].id}
        visible_capability_benchmarks = set(
            isolated.execute(
                select(GovernedAIProviderCapabilityBenchmark.id).where(
                    GovernedAIProviderCapabilityBenchmark.id.in_(
                        [row.id for row in capability_benchmarks]
                    )
                )
            ).scalars()
        )
        visible_capability_events = set(
            isolated.execute(
                select(GovernedAIProviderCapabilityEvent.id).where(
                    GovernedAIProviderCapabilityEvent.id.in_(
                        [row.id for row in capability_events]
                    )
                )
            ).scalars()
        )
        visible_capability_attempts = set(
            isolated.execute(
                select(GovernedAIProviderCapabilityAttempt.id).where(
                    GovernedAIProviderCapabilityAttempt.id.in_(
                        [row.id for row in capability_attempts]
                    )
                )
            ).scalars()
        )
        assert visible_capability_benchmarks == {capability_benchmarks[0].id}
        assert visible_capability_events == {capability_events[0].id}
        assert visible_capability_attempts == {capability_attempts[0].id}
    finally:
        isolated.rollback()
        isolated.close()

    mutation_session = Session(
        bind=db_session.get_bind(), autoflush=False, autocommit=False
    )
    try:
        set_session_security_context(
            mutation_session,
            tenant_id=str(user_a.tenant_id),
            organization_id=str(user_a.tenant_id),
            user_id=user_a.id,
            platform_access=False,
        )
        with pytest.raises(DBAPIError):
            mutation_session.execute(
                update(GovernedAIProviderRoutingReadiness)
                .where(
                    GovernedAIProviderRoutingReadiness.id == readiness_rows[0].id
                )
                .values(routing_enabled=True)
            )
            mutation_session.flush()
    finally:
        mutation_session.rollback()
        mutation_session.close()

    canary_mutation = Session(
        bind=db_session.get_bind(), autoflush=False, autocommit=False
    )
    try:
        set_session_security_context(
            canary_mutation,
            tenant_id=str(user_a.tenant_id),
            organization_id=str(user_a.tenant_id),
            user_id=user_a.id,
            platform_access=False,
        )
        with pytest.raises(DBAPIError):
            canary_mutation.execute(
                update(GovernedAIProviderCanaryEvent)
                .where(GovernedAIProviderCanaryEvent.id == canary_events[0].id)
                .values(traffic_percentage=100)
            )
            canary_mutation.flush()
    finally:
        canary_mutation.rollback()
        canary_mutation.close()

    health_mutation = Session(
        bind=db_session.get_bind(), autoflush=False, autocommit=False
    )
    try:
        set_session_security_context(
            health_mutation,
            tenant_id=str(user_a.tenant_id),
            organization_id=str(user_a.tenant_id),
            user_id=user_a.id,
            platform_access=False,
        )
        with pytest.raises(DBAPIError):
            health_mutation.execute(
                update(GovernedAIProviderCanaryHealthSnapshot)
                .where(
                    GovernedAIProviderCanaryHealthSnapshot.id
                    == canary_health_rows[0].id
                )
                .values(capability_change_allowed=True)
            )
            health_mutation.flush()
    finally:
        health_mutation.rollback()
        health_mutation.close()

    capability_mutation = Session(
        bind=db_session.get_bind(), autoflush=False, autocommit=False
    )
    try:
        set_session_security_context(
            capability_mutation,
            tenant_id=str(user_a.tenant_id),
            organization_id=str(user_a.tenant_id),
            user_id=user_a.id,
            platform_access=False,
        )
        with pytest.raises(DBAPIError):
            capability_mutation.execute(
                update(GovernedAIProviderCapabilityEvent)
                .where(
                    GovernedAIProviderCapabilityEvent.id == capability_events[0].id
                )
                .values(traffic_percentage=100)
            )
            capability_mutation.flush()
    finally:
        capability_mutation.rollback()
        capability_mutation.close()
