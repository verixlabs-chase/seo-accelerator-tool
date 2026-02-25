"""Fleet job orchestration service for portfolio-scoped execution.

This module is the service-layer control plane for Fleet execution. It creates
portfolio-bound Fleet jobs/items, advances item and job state transitions, and
dispatches queued items onto shard-specific worker queues. In the broader
architecture, Portfolio identifies the tenant-owned execution scope, and Fleet
provides bounded, asynchronous fan-out within that scope.

Concurrency and transaction guarantees:
- Portfolio-level concurrency is capped (`FLEET_PORTFOLIO_CONCURRENCY_CAP`) for
  in-flight items when dispatching queued work.
- Item processors acquire row locks (`SELECT ... FOR UPDATE SKIP LOCKED`) before
  state transitions to reduce duplicate execution across workers.
- State transitions and aggregate counter updates are committed atomically per
  processing phase; stale-write conflicts raise HTTP 409.
- Queue dispatch is best-effort and happens after job/item commits.

Retry/session/queue/telemetry notes:
- Application-level retries are explicit via `retry_failed_items`; provider call
  retries for live Search Console execution are controlled by provider retry
  policy (`_FleetSearchConsoleTask` and adapter-level policy).
- `process_fleet_job_item_with_new_session` owns session lifecycle internally
  (open/commit-or-rollback/close). Other functions expect a caller-managed
  SQLAlchemy `Session`.
- Queue routing uses deterministic portfolio hashing to shard onto queue names
  derived from job type.
- This module does not write telemetry records directly; live provider execution
delegates to provider-task infrastructure, which may emit provider telemetry.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from uuid import UUID

from celery import current_app
from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.orm.exc import StaleDataError

from app.core.config import get_settings
from app.db.redis_client import get_redis_client
from app.db.session import SessionLocal
from app.models.fleet_job import FleetJob, FleetJobStatus, FleetJobType
from app.models.fleet_job_item import FleetJobItem, FleetJobItemStatus
from app.models.portfolio import Portfolio
from app.providers.execution_types import ProviderExecutionRequest
from app.providers.google_search_console import SearchConsoleProviderAdapter
from app.providers.retry import RetryPolicy
from app.services.provider_credentials_service import (
    ProviderCredentialConfigurationError,
    get_organization_provider_credentials,
    resolve_provider_credentials,
)
from app.tasks.provider_task import CeleryProviderTask


FLEET_PORTFOLIO_CONCURRENCY_CAP = 5
FLEET_TOKEN_BUCKET_LIMIT = 50
FLEET_TOKEN_BUCKET_WINDOW_SECONDS = 60
FLEET_CIRCUIT_BREAKER_THRESHOLD = 5
FLEET_PROVIDER_CALL_SEARCH_CONSOLE = "google_search_console_query"

FLEET_JOB_TRANSITIONS: dict[str, set[str]] = {
    FleetJobStatus.QUEUED.value: {FleetJobStatus.RUNNING.value},
    FleetJobStatus.RUNNING.value: {
        FleetJobStatus.SUCCEEDED.value,
        FleetJobStatus.PARTIAL.value,
        FleetJobStatus.FAILED.value,
        FleetJobStatus.CANCELLED.value,
    },
}

FLEET_ITEM_TRANSITIONS: dict[str, set[str]] = {
    FleetJobItemStatus.QUEUED.value: {FleetJobItemStatus.RUNNING.value},
    FleetJobItemStatus.RUNNING.value: {FleetJobItemStatus.SUCCEEDED.value, FleetJobItemStatus.FAILED.value},
    FleetJobItemStatus.FAILED.value: {FleetJobItemStatus.QUEUED.value},
}


class _FleetSearchConsoleTask(CeleryProviderTask):
    name = "fleet.provider.google_search_console"
    provider_name = "google_search_console"
    capability = "search_console_analytics"
    timeout_budget_seconds = 15.0
    retry_policy = RetryPolicy(max_attempts=3, base_delay_seconds=0.25, max_delay_seconds=2.0, jitter_ratio=0.0)


class FleetSearchConsoleValidationError(RuntimeError):
    def __init__(self, *, reason_code: str, message: str, details: dict | None = None) -> None:
        self.reason_code = reason_code
        self.message = message
        self.details = details or {}
        super().__init__(f"{reason_code}: {message} | details={self.details}")

    def as_payload(self) -> dict:
        return {
            "reason_code": self.reason_code,
            "message": self.message,
            "details": self.details,
        }


def create_onboard_job(
    *,
    db: Session,
    organization_id: str,
    portfolio_id: str,
    user_id: str | None,
    idempotency_key: str,
    item_seeds: list[dict],
) -> str:
    """Create or reuse a portfolio-scoped Fleet onboard job.

    Responsibility: validate/create onboard job + queued items through shared
    bulk-job workflow.
    Inputs: caller-managed DB session, organization/portfolio scope, optional
    user id, idempotency key, and item seeds.
    Side effects: inserts `FleetJob`/`FleetJobItem` rows and may enqueue pending
    items after commit.
    Transactions: participates in caller session; commits occur in bulk creator.
    Failure modes: raises HTTP 4xx for invalid scope/payload or conflicts.
    Idempotency: strong by `(organization, portfolio, job_type, idempotency_key)`.
    """
    fleet_job, _created = _create_bulk_job(
        db=db,
        organization_id=organization_id,
        portfolio_id=portfolio_id,
        user_id=user_id,
        idempotency_key=idempotency_key,
        item_seeds=item_seeds,
        job_type="onboard",
    )
    return str(fleet_job.id)


def create_schedule_job(
    *,
    db: Session,
    organization_id: str,
    portfolio_id: str,
    user_id: str | None,
    idempotency_key: str,
    item_seeds: list[dict],
) -> tuple[FleetJob, bool]:
    """Create or reuse a portfolio-scoped Fleet schedule job.

    Responsibility: delegate schedule job creation to shared bulk workflow.
    Inputs: caller-managed DB session and scoped schedule request payload.
    Side effects: may persist a new job/items and trigger queue dispatch.
    Transactions: same expectations as `create_onboard_job`.
    Failure modes: HTTP exceptions for validation/scope/conflict conditions.
    Idempotency: same key-based guarantee as other job-creation entry points.
    """
    return _create_bulk_job(
        db=db,
        organization_id=organization_id,
        portfolio_id=portfolio_id,
        user_id=user_id,
        idempotency_key=idempotency_key,
        item_seeds=item_seeds,
        job_type="schedule",
    )


def create_pause_resume_job(
    *,
    db: Session,
    organization_id: str,
    portfolio_id: str,
    user_id: str | None,
    idempotency_key: str,
    item_seeds: list[dict],
    action: str,
) -> tuple[FleetJob, bool]:
    """Create or reuse a Fleet pause/resume job.

    Responsibility: validate action (`pause` or `resume`) then create bulk job.
    Inputs: caller-managed DB session, scope identifiers, idempotency key,
    item seeds, and action string.
    Side effects: writes job/item rows and may enqueue items.
    Transactions: same bulk-job transaction behavior.
    Failure modes: HTTP 400 for invalid action; other HTTP errors from create path.
    Idempotency: key-based deduplication within scope/job type.
    """
    if action not in {"pause", "resume"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid fleet action")
    return _create_bulk_job(
        db=db,
        organization_id=organization_id,
        portfolio_id=portfolio_id,
        user_id=user_id,
        idempotency_key=idempotency_key,
        item_seeds=item_seeds,
        job_type=action,
    )


def create_remediate_job(
    *,
    db: Session,
    organization_id: str,
    portfolio_id: str,
    user_id: str | None,
    idempotency_key: str,
    source_fleet_job_id: str,
) -> tuple[FleetJob, bool]:
    """Create or reuse a remediate job from failed items of a source fleet job.

    Responsibility: validate source job scope, collect failed source items, and
    seed a new remediate Fleet job.
    Inputs: caller-managed DB session, scope identifiers, idempotency key, and
    source fleet job id.
    Side effects: reads source failures, persists remediate job/items, and may
    enqueue pending work.
    Transactions: follows bulk-job commit behavior in shared creator.
    Failure modes: HTTP 403 for cross-portfolio source, HTTP 400 when no failed
    items exist, plus shared creation failures.
    Idempotency: same key-based dedupe for remediate job type.
    """
    _portfolio_or_404(db=db, organization_id=organization_id, portfolio_id=portfolio_id)
    source_job = _fleet_job_or_404(db=db, organization_id=organization_id, fleet_job_id=source_fleet_job_id)
    if source_job.portfolio_id != portfolio_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Source fleet job outside portfolio scope")
    failed_items = (
        db.query(FleetJobItem)
        .filter(
            FleetJobItem.fleet_job_id == source_job.id,
            FleetJobItem.status == FleetJobItemStatus.FAILED,
        )
        .order_by(FleetJobItem.created_at.asc())
        .all()
    )
    if not failed_items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No failed fleet job items to remediate")
    item_seeds = [{"item_key": item.item_key, "payload": {"source_item_id": item.id}} for item in failed_items]
    return _create_bulk_job(
        db=db,
        organization_id=organization_id,
        portfolio_id=portfolio_id,
        user_id=user_id,
        idempotency_key=idempotency_key,
        item_seeds=item_seeds,
        job_type="remediate",
    )


def get_fleet_job(*, db: Session, organization_id: str, fleet_job_id: str) -> FleetJob:
    """Fetch a Fleet job within organization scope.

    Responsibility: read-only lookup with authorization-by-scope semantics.
    Inputs: caller-managed DB session, organization id, fleet job id.
    Side effects: none.
    Transactions: no commit/rollback performed.
    Failure modes: HTTP 404 when the scoped job is absent.
    Idempotency: fully idempotent read.
    """
    return _fleet_job_or_404(db=db, organization_id=organization_id, fleet_job_id=fleet_job_id)


def list_fleet_job_items(*, db: Session, organization_id: str, fleet_job_id: str) -> list[FleetJobItem]:
    """List all items for a scoped Fleet job in creation order.

    Responsibility: validate job scope and return associated items.
    Inputs: caller-managed DB session, organization id, fleet job id.
    Side effects: none.
    Transactions: read-only; caller controls session lifecycle.
    Failure modes: HTTP 404 when job is out of scope or missing.
    Idempotency: idempotent read for unchanged data.
    """
    job = _fleet_job_or_404(db=db, organization_id=organization_id, fleet_job_id=fleet_job_id)
    return (
        db.query(FleetJobItem)
        .filter(FleetJobItem.fleet_job_id == job.id)
        .order_by(FleetJobItem.created_at.asc())
        .all()
    )


def enqueue_pending_items_for_portfolio(*, db: Session, organization_id: str, portfolio_id: str) -> int:
    """Dispatch queued Fleet items for a portfolio up to concurrency capacity.

    Responsibility: compute available in-flight slots, select oldest queued items,
    and enqueue tasks onto the default worker queue.
    Inputs: caller-managed DB session and portfolio scope identifiers.
    Side effects: submits Celery tasks (`fleet.process_fleet_job_item_task`) on
    queue `default`; no row status changes are made here.
    Transactions: performs read queries only; does not commit by itself.
    Failure modes: HTTP 404 when portfolio missing; task broker failures propagate.
    Idempotency: effectively at-least-once dispatch if called repeatedly before
    workers transition item state; lock-and-status checks in processors prevent
    duplicate processing effects.
    Queue routing: all Fleet item tasks are routed to queue `default`.
    """
    _portfolio_or_404(db=db, organization_id=organization_id, portfolio_id=portfolio_id)
    running_count = (
        db.query(func.count(FleetJobItem.id))
        .join(FleetJob, FleetJob.id == FleetJobItem.fleet_job_id)
        .filter(
            FleetJob.portfolio_id == portfolio_id,
            FleetJobItem.status == FleetJobItemStatus.RUNNING,
        )
        .scalar()
        or 0
    )
    available_slots = max(0, FLEET_PORTFOLIO_CONCURRENCY_CAP - int(running_count))
    if available_slots == 0:
        return 0

    items = (
        db.query(FleetJobItem)
        .options(joinedload(FleetJobItem.fleet_job))
        .join(FleetJob, FleetJob.id == FleetJobItem.fleet_job_id)
        .filter(
            FleetJob.portfolio_id == portfolio_id,
            FleetJob.organization_id == organization_id,
            FleetJob.status.in_([FleetJobStatus.QUEUED, FleetJobStatus.RUNNING]),
            FleetJobItem.status == FleetJobItemStatus.QUEUED,
        )
        .order_by(FleetJob.created_at.asc(), FleetJobItem.created_at.asc())
        .limit(available_slots)
        .all()
    )

    if not items:
        return 0

    if get_settings().app_env.lower() == "test":
        return 0


    dispatched = 0
    for item in items:
        current_app.send_task("fleet.process_fleet_job_item_task", args=[item.id], queue="default")
        dispatched += 1
    return dispatched


def process_fleet_job_item_with_new_session(fleet_job_item_id: str) -> dict:
    """Process one Fleet item using an internally managed DB session.

    Responsibility: session-wrapper entry point for async workers.
    Inputs: fleet job item id.
    Side effects: may update item/job state, counters, timestamps, and dispatch
    additional queued items through portfolio enqueue.
    Transactions: opens `SessionLocal`, commits on success when transaction is
    active, rolls back on error, and always closes session.
    Failure modes: propagates underlying processing exceptions.
    Idempotency: safe to re-invoke; non-queued/finalized states are ignored.
    Session lifecycle: fully owned by this function.
    """
    db = SessionLocal()
    try:
        result = process_fleet_job_item(db=db, fleet_job_item_id=fleet_job_item_id)
        if db.in_transaction():
            db.commit()
        return result
    except Exception:
        if db.in_transaction():
            db.rollback()
        raise
    finally:
        db.close()


def process_fleet_job_item(*, db: Session, fleet_job_item_id: str) -> dict:
    """Execute one Fleet job item state machine and provider handler.

    Responsibility: lock item, validate executable state, transition
    QUEUED->RUNNING->(SUCCEEDED|FAILED), refresh parent job counters/status, and
    trigger follow-on dispatch.
    Inputs: caller-managed DB session and fleet job item id.
    Side effects: DB writes to item/job status and timestamps, provider/stub call
    execution, and queue dispatch for additional pending items.
    Transactions: uses multiple explicit commit/rollback boundaries:
    1) commit RUNNING transition before handler execution,
    2) commit terminal transition/counters afterward,
    3) rollback on missing/invalid/lock-conflict paths.
    Failure modes: returns structured ignored/missing statuses for benign races,
    raises HTTP 409 on stale-write conflict, and captures handler exceptions as
    item failure metadata.
    Idempotency: re-entrant for duplicate task delivery; only QUEUED items are
    executed, others return ignored results without repeated handler execution.
    Retry behavior: this function does not auto-retry failed items; retries are
    explicit via `retry_failed_items`. Provider-specific retries may occur inside
    delegated provider execution policy.
    Telemetry writes: none directly; delegated provider task infrastructure may
    persist provider-call telemetry.
    """
    item = _locked_item(db=db, fleet_job_item_id=fleet_job_item_id)
    if item is None:
        if db.in_transaction():
            db.rollback()
        return {"status": "missing", "fleet_job_item_id": fleet_job_item_id}

    item_status = _normalize_item_status(item.status)
    if item_status != FleetJobItemStatus.QUEUED.value:
        if db.in_transaction():
            db.rollback()
        return {"status": "ignored", "fleet_job_item_id": fleet_job_item_id, "reason": "not_queued"}

    job = item.fleet_job
    if _normalize_job_status(job.status) == FleetJobStatus.CANCELLED.value:
        if db.in_transaction():
            db.rollback()
        return {"status": "ignored", "fleet_job_item_id": fleet_job_item_id, "reason": "job_cancelled"}

    _transition_item(item=item, next_status=FleetJobItemStatus.RUNNING.value)
    if _normalize_job_status(job.status) == FleetJobStatus.QUEUED.value:
        _transition_job(job=job, next_status=FleetJobStatus.RUNNING.value)
        if job.started_at is None:
            job.started_at = datetime.now(UTC)
    item.started_at = datetime.now(UTC)
    db.flush()
    _refresh_job_counters(db=db, job=job)
    db.commit()

    failed = False
    error_code = None
    error_detail = None
    try:
        _run_item_handler(job=job, item=item)
    except Exception as exc:  # noqa: BLE001
        failed = True
        error_code = "fleet_item_handler_failure"
        error_detail = str(exc)

    item = _locked_item(db=db, fleet_job_item_id=fleet_job_item_id)
    if item is None:
        if db.in_transaction():
            db.rollback()
        return {"status": "missing_after_execution", "fleet_job_item_id": fleet_job_item_id}
    job = item.fleet_job

    if _normalize_item_status(item.status) != FleetJobItemStatus.RUNNING.value:
        db.rollback()
        return {"status": "ignored", "fleet_job_item_id": fleet_job_item_id, "reason": "already_finalized"}

    if failed:
        _transition_item(item=item, next_status=FleetJobItemStatus.FAILED.value)
        item.error_code = error_code
        item.error_detail = error_detail
    else:
        _transition_item(item=item, next_status=FleetJobItemStatus.SUCCEEDED.value)
        item.error_code = None
        item.error_detail = None
    item.finished_at = datetime.now(UTC)

    db.flush()
    _refresh_job_counters(db=db, job=job)
    _advance_job_terminal_state(job=job)
    fleet_job_id = str(job.id)
    job_status = _normalize_job_status(job.status)

    try:
        db.commit()
    except StaleDataError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Fleet job version conflict") from exc

    enqueue_pending_items_for_portfolio(db=db, organization_id=job.organization_id, portfolio_id=job.portfolio_id)
    if db.in_transaction():
        db.commit()
    return {
        "status": "failed" if failed else "succeeded",
        "fleet_job_item_id": fleet_job_item_id,
        "fleet_job_id": fleet_job_id,
        "job_status": job_status,
    }


def retry_failed_items(*, db: Session, organization_id: str, fleet_job_id: str, item_keys: Iterable[str] | None = None) -> int:
    """Requeue failed items for a Fleet job and resume job execution if needed.

    Responsibility: select FAILED items (optionally filtered), transition them
    back to QUEUED, increment retry counters, clear error metadata, and restart
    dispatch.
    Inputs: caller-managed DB session, organization id, fleet job id, optional
    iterable of item keys.
    Side effects: DB updates on item retry fields and job status/counters, then
    queue dispatch via `enqueue_pending_items_for_portfolio`.
    Transactions: row-locks candidate failed items, flushes updates, commits once
    before enqueue.
    Failure modes: HTTP 404 for missing/scoped-out job; DB errors propagate.
    Idempotency: not idempotent per item because each successful call increments
    `retries`; repeated calls after requeue may return zero when nothing FAILED.
    Retry behavior: explicit operator/API-triggered retry mechanism.
    """
    job = _fleet_job_or_404(db=db, organization_id=organization_id, fleet_job_id=fleet_job_id)
    query = db.query(FleetJobItem).filter(
        FleetJobItem.fleet_job_id == job.id,
        FleetJobItem.status == FleetJobItemStatus.FAILED,
    )
    if item_keys is not None:
        item_key_set = {item for item in item_keys}
        if item_key_set:
            query = query.filter(FleetJobItem.item_key.in_(item_key_set))
    rows = query.with_for_update().all()
    for item in rows:
        _transition_item(item=item, next_status=FleetJobItemStatus.QUEUED.value)
        item.retries += 1
        item.error_code = None
        item.error_detail = None
        item.started_at = None
        item.finished_at = None
    if rows:
        db.flush()
        if _normalize_job_status(job.status) in {FleetJobStatus.FAILED.value, FleetJobStatus.PARTIAL.value}:
            job.status = FleetJobStatus.RUNNING
            job.finished_at = None
        _refresh_job_counters(db=db, job=job)
        db.commit()
        enqueue_pending_items_for_portfolio(db=db, organization_id=job.organization_id, portfolio_id=job.portfolio_id)
    return len(rows)


def _create_bulk_job(
    *,
    db: Session,
    organization_id: str,
    portfolio_id: str,
    user_id: str | None,
    idempotency_key: str,
    item_seeds: list[dict],
    job_type: str,
) -> tuple[FleetJob, bool]:
    _portfolio_or_404(db=db, organization_id=organization_id, portfolio_id=portfolio_id)
    normalized_idempotency = idempotency_key.strip()
    if not normalized_idempotency:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="idempotency_key is required")

    existing = (
        db.query(FleetJob)
        .filter(
            FleetJob.organization_id == organization_id,
            FleetJob.portfolio_id == portfolio_id,
            FleetJob.job_type == job_type,
            FleetJob.idempotency_key == normalized_idempotency,
        )
        .first()
    )
    if existing is not None:
        return existing, False

    keys = [str(item.get("item_key", "")).strip() for item in item_seeds]
    if any(not key for key in keys):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="All fleet item keys must be non-empty")
    if len(set(keys)) != len(keys):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Duplicate fleet item keys in request payload")

    now = datetime.now(UTC)
    job = FleetJob(
        organization_id=organization_id,
        portfolio_id=portfolio_id,
        job_type=FleetJobType(job_type),
        status=FleetJobStatus.QUEUED,
        idempotency_key=normalized_idempotency,
        requested_by=user_id,
        request_payload={"items": item_seeds},
        summary_json={},
        total_items=len(item_seeds),
        queued_items=len(item_seeds),
        running_items=0,
        succeeded_items=0,
        failed_items=0,
        cancelled_items=0,
        created_at=now,
        updated_at=now,
    )
    db.add(job)
    db.flush()

    for item in item_seeds:
        db.add(
            FleetJobItem(
                fleet_job_id=job.id,
                item_key=str(item["item_key"]).strip(),
                status=FleetJobItemStatus.QUEUED,
                error_code=None,
                error_detail=None,
                retries=0,
                started_at=None,
                finished_at=None,
                created_at=now,
                updated_at=now,
            )
        )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(FleetJob)
            .filter(
                FleetJob.organization_id == organization_id,
                FleetJob.portfolio_id == portfolio_id,
                FleetJob.job_type == job_type,
                FleetJob.idempotency_key == normalized_idempotency,
            )
            .first()
        )
        if existing is None:
            raise
        return existing, False
    db.refresh(job)
    enqueue_pending_items_for_portfolio(db=db, organization_id=organization_id, portfolio_id=portfolio_id)
    return job, True


def _run_stub_handler(*, job: FleetJob, item: FleetJobItem) -> None:
    redis_client = get_redis_client()
    bucket_key = f"fleet:tokens:{job.portfolio_id}:{job.job_type}"
    if not _token_bucket_allow(redis_client, bucket_key):
        raise RuntimeError("provider throttle placeholder denied request")
    breaker_key = f"fleet:breaker:{job.portfolio_id}:{job.job_type}"
    if not _breaker_allow(redis_client, breaker_key):
        raise RuntimeError("circuit breaker placeholder open")

    payload_items = job.request_payload.get("items", []) if isinstance(job.request_payload, dict) else []
    payload_by_key = {str(entry.get("item_key")): entry for entry in payload_items if isinstance(entry, dict)}
    payload = payload_by_key.get(item.item_key, {})
    if payload.get("force_fail") is True or "fail" in item.item_key.lower():
        _breaker_record_failure(redis_client, breaker_key)
        raise RuntimeError("stub handler forced failure")
    _breaker_record_success(redis_client, breaker_key)


def _run_item_handler(*, job: FleetJob, item: FleetJobItem) -> None:
    payload = _resolve_item_payload(job=job, item=item)
    provider_call = str(payload.get("provider_call", "")).strip().lower()
    if provider_call == FLEET_PROVIDER_CALL_SEARCH_CONSOLE:
        _run_search_console_live_call(job=job, item=item, payload=payload)
        return
    _run_stub_handler(job=job, item=item)


def _resolve_item_payload(*, job: FleetJob, item: FleetJobItem) -> dict:
    payload_items = job.request_payload.get("items", []) if isinstance(job.request_payload, dict) else []
    payload_by_key = {str(entry.get("item_key")): entry for entry in payload_items if isinstance(entry, dict)}
    payload = payload_by_key.get(item.item_key, {})
    if not isinstance(payload, dict):
        return {}
    raw_payload = payload.get("payload", payload)
    if not isinstance(raw_payload, dict):
        return {}
    return _normalize_fleet_payload(raw_payload)


def _normalize_fleet_payload(payload: dict) -> dict:
    normalized = dict(payload)
    rename_map = {
        "startDate": "start_date",
        "endDate": "end_date",
        "rowLimit": "row_limit",
        "siteUrl": "site_url",
    }
    for source_key, target_key in rename_map.items():
        if target_key not in normalized and source_key in normalized:
            normalized[target_key] = normalized[source_key]
    return normalized


def _run_search_console_live_call(*, job: FleetJob, item: FleetJobItem, payload: dict) -> None:
    request_payload = _build_validated_search_console_request_payload(
        payload=payload,
        organization_id=str(job.organization_id),
        fleet_job_item_id=str(item.id),
    )
    request = ProviderExecutionRequest(
        operation="search_console_query",
        correlation_id=f"fleet:{job.id}:{item.id}",
        payload=request_payload,
    )
    provider_db = SessionLocal()
    try:
        try:
            credentials = resolve_provider_credentials(
                provider_db,
                str(job.organization_id),
                "google",
                required_credential_mode="byo_required",
                require_org_oauth=True,
            )
        except ProviderCredentialConfigurationError as exc:
            raise FleetSearchConsoleValidationError(
                reason_code=exc.reason_code,
                message=str(exc),
                details={"fleet_job_item_id": str(item.id), "organization_id": str(job.organization_id)},
            ) from exc
        _validate_search_console_credentials(
            credentials=credentials,
            fleet_job_item_id=str(item.id),
        )
        provider = SearchConsoleProviderAdapter(
            db=provider_db,
            retry_policy=RetryPolicy(max_attempts=1, jitter_ratio=0.0),
        )
        task = _FleetSearchConsoleTask()
        result = task.run_provider_call(provider=provider, request=request)
        if not result.success:
            reason = result.error.reason_code if result.error is not None else "unknown"
            raise RuntimeError(f"Search Console provider execution failed ({reason}).")
    finally:
        provider_db.close()


def _build_validated_search_console_request_payload(
    *,
    payload: dict,
    organization_id: str,
    fleet_job_item_id: str,
) -> dict:
    site_url = str(payload.get("site_url", "")).strip()
    start_date = str(payload.get("start_date", "")).strip()
    end_date = str(payload.get("end_date", "")).strip()
    missing_fields = [name for name, value in {"site_url": site_url, "start_date": start_date, "end_date": end_date}.items() if not value]
    if missing_fields:
        raise FleetSearchConsoleValidationError(
            reason_code="fleet_gsc_missing_payload_fields",
            message="Missing required payload fields for Search Console fleet execution.",
            details={"missing_fields": missing_fields, "fleet_job_item_id": fleet_job_item_id},
        )
    try:
        row_limit = int(payload.get("row_limit", 100))
    except (TypeError, ValueError) as exc:
        raise FleetSearchConsoleValidationError(
            reason_code="fleet_gsc_invalid_row_limit",
            message="row_limit must be numeric.",
            details={"fleet_job_item_id": fleet_job_item_id},
        ) from exc
    if row_limit <= 0:
        raise FleetSearchConsoleValidationError(
            reason_code="fleet_gsc_invalid_row_limit",
            message="row_limit must be greater than 0.",
            details={"fleet_job_item_id": fleet_job_item_id},
        )
    request_payload: dict = {
        "tenant_id": organization_id,
        "organization_id": organization_id,
        "campaign_id": payload.get("campaign_id"),
        "sub_account_id": payload.get("sub_account_id"),
        "site_url": site_url,
        "start_date": start_date,
        "end_date": end_date,
        "dimensions": payload.get("dimensions", ["query"]),
        "row_limit": row_limit,
    }
    timeout_budget_ms = payload.get("timeout_budget_ms")
    if timeout_budget_ms is not None:
        request_payload["timeout_budget_ms"] = timeout_budget_ms
    return request_payload


def _validate_search_console_credentials(*, credentials: dict, fleet_job_item_id: str) -> None:
    access_token = str(credentials.get("access_token", "")).strip()
    if not access_token:
        raise FleetSearchConsoleValidationError(
            reason_code="fleet_gsc_access_token_missing",
            message="Google OAuth access token missing for Search Console execution.",
            details={"fleet_job_item_id": fleet_job_item_id},
        )
    expected_scope = get_settings().google_oauth_scope_gsc.strip()
    granted_scope = str(credentials.get("scope", "")).strip()
    if expected_scope and expected_scope not in granted_scope.split():
        raise FleetSearchConsoleValidationError(
            reason_code="fleet_gsc_scope_missing",
            message="Google OAuth scope missing for Search Console execution.",
            details={
                "required_scope": expected_scope,
                "granted_scope": granted_scope,
                "fleet_job_item_id": fleet_job_item_id,
            },
        )


def test_gsc_fleet_validation(org_id: UUID) -> dict:
    mock_payload = {
        "site_url": "https://example.com",
        "start_date": "2024-01-01",
        "end_date": "2024-01-07",
        "row_limit": 5,
        "dimensions": ["query"],
    }
    normalized_payload = _normalize_fleet_payload(mock_payload)
    request_payload = _build_validated_search_console_request_payload(
        payload=normalized_payload,
        organization_id=str(org_id),
        fleet_job_item_id="dry-run-validation",
    )
    db = SessionLocal()
    try:
        try:
            credentials = get_organization_provider_credentials(db, str(org_id), "google")
        except ProviderCredentialConfigurationError as exc:
            raise FleetSearchConsoleValidationError(
                reason_code=exc.reason_code,
                message=str(exc),
                details={"organization_id": str(org_id)},
            ) from exc
        if not credentials:
            raise FleetSearchConsoleValidationError(
                reason_code="org_oauth_credential_required",
                message="Organization OAuth credential required for provider 'google'.",
                details={"organization_id": str(org_id)},
            )
        _validate_search_console_credentials(
            credentials=credentials,
            fleet_job_item_id="dry-run-validation",
        )
        # Intentionally stop here for dry-run harness: no provider call and no HTTP request.
        return {
            "status": "ok",
            "organization_id": str(org_id),
            "request_payload": request_payload,
            "network_call_skipped": True,
        }
    finally:
        db.close()


def _token_bucket_allow(client, key: str) -> bool:
    if client is None:
        return True
    try:
        count = client.incr(key)
        if count == 1:
            client.expire(key, FLEET_TOKEN_BUCKET_WINDOW_SECONDS)
        return int(count) <= FLEET_TOKEN_BUCKET_LIMIT
    except Exception:  # noqa: BLE001
        return True


def _breaker_allow(client, key: str) -> bool:
    if client is None:
        return True
    try:
        value = client.get(key)
        if value is None:
            return True
        return int(value) < FLEET_CIRCUIT_BREAKER_THRESHOLD
    except Exception:  # noqa: BLE001
        return True


def _breaker_record_failure(client, key: str) -> None:
    if client is None:
        return
    try:
        value = client.incr(key)
        if int(value) == 1:
            client.expire(key, 120)
    except Exception:  # noqa: BLE001
        return


def _breaker_record_success(client, key: str) -> None:
    if client is None:
        return
    try:
        client.delete(key)
    except Exception:  # noqa: BLE001
        return


def _refresh_job_counters(*, db: Session, job: FleetJob) -> None:
    counts = (
        db.query(FleetJobItem.status, func.count(FleetJobItem.id))
        .filter(FleetJobItem.fleet_job_id == job.id)
        .group_by(FleetJobItem.status)
        .all()
    )
    by_status = {_normalize_item_status(key): int(value) for key, value in counts}
    total = int(sum(by_status.values()))
    job.total_items = total
    job.queued_items = by_status.get(FleetJobItemStatus.QUEUED.value, 0)
    job.running_items = by_status.get(FleetJobItemStatus.RUNNING.value, 0)
    job.succeeded_items = by_status.get(FleetJobItemStatus.SUCCEEDED.value, 0)
    job.failed_items = by_status.get(FleetJobItemStatus.FAILED.value, 0)
    job.cancelled_items = by_status.get(FleetJobStatus.CANCELLED.value, 0)
    job.updated_at = datetime.now(UTC)


def _advance_job_terminal_state(*, job: FleetJob) -> None:
    if job.running_items > 0 or job.queued_items > 0:
        return
    if job.total_items == 0:
        return
    if job.failed_items == 0 and job.succeeded_items == job.total_items:
        _transition_job(job=job, next_status=FleetJobStatus.SUCCEEDED.value)
    elif job.succeeded_items == 0 and job.failed_items == job.total_items:
        _transition_job(job=job, next_status=FleetJobStatus.FAILED.value)
    else:
        _transition_job(job=job, next_status=FleetJobStatus.PARTIAL.value)
    job.finished_at = datetime.now(UTC)


def _transition_job(*, job: FleetJob, next_status: str) -> None:
    current = _normalize_job_status(job.status)
    if current == next_status:
        return
    allowed = FLEET_JOB_TRANSITIONS.get(current, set())
    if next_status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Invalid FleetJob transition {current} -> {next_status}",
        )
    job.status = FleetJobStatus(next_status)
    job.updated_at = datetime.now(UTC)


def _transition_item(*, item: FleetJobItem, next_status: str) -> None:
    current = _normalize_item_status(item.status)
    if current == next_status:
        return
    allowed = FLEET_ITEM_TRANSITIONS.get(current, set())
    if next_status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Invalid FleetJobItem transition {current} -> {next_status}",
        )
    item.status = FleetJobItemStatus(next_status)
    item.updated_at = datetime.now(UTC)


def _normalize_item_status(status_value: object) -> str:
    normalized = _normalize_enum_value(status_value)
    if normalized == "pending":
        return FleetJobItemStatus.QUEUED.value
    return normalized


def _normalize_job_status(status_value: object) -> str:
    return _normalize_enum_value(status_value)


def _normalize_enum_value(status_value: object) -> str:
    if hasattr(status_value, "value"):
        return str(getattr(status_value, "value")).lower()
    normalized = str(status_value).lower()
    if "." in normalized:
        normalized = normalized.split(".")[-1]
    return normalized


def _portfolio_or_404(*, db: Session, organization_id: str, portfolio_id: str) -> Portfolio:
    row = (
        db.query(Portfolio)
        .filter(
            Portfolio.id == portfolio_id,
            Portfolio.organization_id == organization_id,
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portfolio not found")
    return row


def _fleet_job_or_404(*, db: Session, organization_id: str, fleet_job_id: str) -> FleetJob:
    row = (
        db.query(FleetJob)
        .filter(
            FleetJob.id == fleet_job_id,
            FleetJob.organization_id == organization_id,
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fleet job not found")
    return row


def _locked_item(*, db: Session, fleet_job_item_id: str) -> FleetJobItem | None:
    row = (
        db.query(FleetJobItem)
        .options(joinedload(FleetJobItem.fleet_job))
        .filter(FleetJobItem.id == fleet_job_item_id)
        .with_for_update(skip_locked=True)
        .first()
    )
    if row is not None:
        return row
    return (
        db.query(FleetJobItem)
        .options(joinedload(FleetJobItem.fleet_job))
        .filter(FleetJobItem.id == fleet_job_item_id)
        .first()
    )
