from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.events import emit_event
from app.models.campaign import Campaign
from app.models.crawl import CrawlRun
from app.models.onboarding_session import OnboardingSession
from app.models.organization import Organization
from app.models.organization_provider_credential import OrganizationProviderCredential
from app.models.reporting import MonthlyReport
from app.models.tenant import Tenant
from app.services import crawl_service, intelligence_service, lifecycle_service, provider_credentials_service, reporting_service
from app.tasks.tasks import crawl_schedule_campaign


INITIALIZED = "INITIALIZED"
ORG_READY = "ORG_READY"
CAMPAIGN_CREATED = "CAMPAIGN_CREATED"
PROVIDER_CONNECTED = "PROVIDER_CONNECTED"
CRAWL_STARTED = "CRAWL_STARTED"
REPORT_GENERATED = "REPORT_GENERATED"
AUTOMATION_ENABLED = "AUTOMATION_ENABLED"
COMPLETED = "COMPLETED"
FAILED = "FAILED"

IN_PROGRESS_STATUS = "IN_PROGRESS"
COMPLETED_STATUS = "COMPLETED"
FAILED_STATUS = "FAILED"

STATE_SEQUENCE = [
    INITIALIZED,
    ORG_READY,
    CAMPAIGN_CREATED,
    PROVIDER_CONNECTED,
    CRAWL_STARTED,
    REPORT_GENERATED,
    AUTOMATION_ENABLED,
    COMPLETED,
]
NEXT_STATE = {STATE_SEQUENCE[i]: STATE_SEQUENCE[i + 1] for i in range(len(STATE_SEQUENCE) - 1)}


def start_onboarding(
    db: Session,
    payload: dict[str, Any],
    *,
    actor_user_id: str | None = None,
    actor_organization_id: str | None = None,
) -> OnboardingSession:
    tenant_name = str(payload.get("tenant_name", "")).strip()
    if not tenant_name:
        raise ValueError("tenant_name is required")

    existing_tenant = db.query(Tenant).filter(Tenant.name == tenant_name).first()
    if existing_tenant is not None:
        existing_session = _latest_session_by_tenant(db, existing_tenant.id)
        if existing_session is not None:
            return existing_session

    session = OnboardingSession(
        status=IN_PROGRESS_STATUS,
        current_step=INITIALIZED,
        step_payload={
            "input": payload,
            "actor": {
                "user_id": actor_user_id,
                "organization_id": actor_organization_id,
            },
            "completed_steps": [],
            "idempotency_keys": {},
            "step_results": {},
            "task_ids": {},
        },
        error_state=None,
        retry_count=0,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return _advance_until_terminal(db, session)


def resume_onboarding(db: Session, tenant_id: str) -> OnboardingSession:
    session = _latest_session_by_tenant(db, tenant_id)
    if session is None:
        raise ValueError("onboarding session not found")
    if session.status == COMPLETED_STATUS:
        return session
    if session.status == FAILED_STATUS:
        resume_from = _resume_from_state(session)
        session.current_step = resume_from
        session.status = IN_PROGRESS_STATUS
        session.error_state = None
        session.updated_at = datetime.now(UTC)
        db.commit()
        db.refresh(session)
    return _advance_until_terminal(db, session)


def get_onboarding_status(db: Session, tenant_id: str) -> OnboardingSession | None:
    return _latest_session_by_tenant(db, tenant_id)


def get_onboarding_actor_scope(session: OnboardingSession | None) -> dict[str, str | None]:
    if session is None:
        return {"user_id": None, "organization_id": None}
    payload = session.step_payload or {}
    actor = payload.get("actor") if isinstance(payload, dict) else None
    if not isinstance(actor, dict):
        return {"user_id": None, "organization_id": None}
    user_id = actor.get("user_id")
    organization_id = actor.get("organization_id")
    return {
        "user_id": user_id if isinstance(user_id, str) else None,
        "organization_id": organization_id if isinstance(organization_id, str) else None,
    }


def run_next_step(db: Session, session: OnboardingSession) -> OnboardingSession:
    if session.status == COMPLETED_STATUS or session.current_step == COMPLETED:
        return session
    if session.status == FAILED_STATUS or session.current_step == FAILED:
        raise ValueError("cannot run next step while session is failed")
    if session.current_step not in NEXT_STATE:
        raise ValueError(f"invalid onboarding step: {session.current_step}")

    previous_step = session.current_step
    target_step = NEXT_STATE[session.current_step]
    idempotency_key = _idempotency_key(session.id, target_step)
    payload = _session_payload(session)
    _store_idempotency_key(payload, target_step, idempotency_key)

    try:
        if target_step == ORG_READY:
            result = _ensure_org_ready(db, session, payload)
        elif target_step == CAMPAIGN_CREATED:
            result = _ensure_campaign_created(db, session, payload)
        elif target_step == PROVIDER_CONNECTED:
            result = _ensure_provider_connected(db, session, payload)
        elif target_step == CRAWL_STARTED:
            result = _ensure_crawl_started(db, session, payload)
        elif target_step == REPORT_GENERATED:
            result = _ensure_report_generated(db, session, payload)
        elif target_step == AUTOMATION_ENABLED:
            result = _ensure_automation_enabled(db, session, payload)
        elif target_step == COMPLETED:
            result = {"status": "complete"}
        else:
            raise ValueError(f"unsupported onboarding step: {target_step}")
    except Exception as exc:  # noqa: BLE001
        session.status = FAILED_STATUS
        session.current_step = FAILED
        session.retry_count += 1
        session.error_state = {
            "step": target_step,
            "resume_from": _last_non_failed_step(previous_step, session.error_state),
            "message": str(exc),
            "error_type": exc.__class__.__name__,
        }
        session.step_payload = payload
        session.updated_at = datetime.now(UTC)
        db.commit()
        db.refresh(session)
        return session

    _mark_step_completed(payload, target_step, result)
    session.step_payload = payload
    if target_step == COMPLETED:
        session.status = COMPLETED_STATUS
        session.current_step = COMPLETED
    else:
        session.status = IN_PROGRESS_STATUS
        session.current_step = target_step
    session.error_state = None
    session.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(session)
    return session


def _advance_until_terminal(db: Session, session: OnboardingSession) -> OnboardingSession:
    guard = 0
    while session.status == IN_PROGRESS_STATUS and session.current_step not in {COMPLETED, FAILED}:
        guard += 1
        if guard > 16:
            break
        session = run_next_step(db, session)
        if session.status == FAILED_STATUS:
            break
    return session


def _ensure_org_ready(db: Session, session: OnboardingSession, payload: dict[str, Any]) -> dict[str, Any]:
    step_results = payload.setdefault("step_results", {})
    if ORG_READY in step_results and session.tenant_id and session.organization_id:
        return dict(step_results[ORG_READY])

    input_payload = _input_payload(payload)
    tenant_name = str(input_payload.get("tenant_name", "")).strip()
    org_name = str(input_payload.get("organization_name", "")).strip()

    tenant = db.get(Tenant, session.tenant_id) if session.tenant_id else None
    if tenant is None:
        tenant = db.query(Tenant).filter(Tenant.name == tenant_name).first()
    if tenant is None:
        tenant = lifecycle_service.create_tenant(db, name=tenant_name)

    organization = db.get(Organization, session.organization_id) if session.organization_id else None
    if organization is None:
        organization = db.query(Organization).filter(Organization.id == tenant.id).first()
    if organization is None:
        organization = Organization(
            id=tenant.id,
            name=org_name or f"org-{tenant.id[:8]}",
            plan_type="standard",
            billing_mode="subscription",
            status="active",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db.add(organization)
        db.commit()
        db.refresh(organization)

    session.tenant_id = tenant.id
    session.organization_id = organization.id
    return {"tenant_id": tenant.id, "organization_id": organization.id}


def _ensure_campaign_created(db: Session, session: OnboardingSession, payload: dict[str, Any]) -> dict[str, Any]:
    step_results = payload.setdefault("step_results", {})
    if CAMPAIGN_CREATED in step_results and session.campaign_id:
        campaign = db.get(Campaign, session.campaign_id)
        if campaign is not None:
            return dict(step_results[CAMPAIGN_CREATED])

    if not session.tenant_id or not session.organization_id:
        raise ValueError("tenant and organization must be ready before campaign creation")

    input_payload = _input_payload(payload)
    name = str(input_payload.get("campaign_name", "")).strip()
    domain = str(input_payload.get("campaign_domain", "")).strip()
    if not name or not domain:
        raise ValueError("campaign_name and campaign_domain are required")

    campaign = (
        db.query(Campaign)
        .filter(
            Campaign.tenant_id == session.tenant_id,
            Campaign.organization_id == session.organization_id,
            Campaign.name == name,
            Campaign.domain == domain,
        )
        .first()
    )
    if campaign is None:
        campaign = Campaign(
            tenant_id=session.tenant_id,
            organization_id=session.organization_id,
            name=name,
            domain=domain,
            sub_account_id=input_payload.get("sub_account_id"),
        )
        db.add(campaign)
        db.flush()
        emit_event(
            db,
            tenant_id=session.tenant_id,
            event_type="campaign.created",
            payload={"campaign_id": campaign.id, "setup_state": campaign.setup_state, "sub_account_id": campaign.sub_account_id},
        )
        db.commit()
        db.refresh(campaign)

    session.campaign_id = campaign.id
    _ensure_campaign_state(db, session.tenant_id, campaign.id, target_state="Configured")
    return {"campaign_id": campaign.id, "setup_state": "Configured"}


def _ensure_provider_connected(db: Session, session: OnboardingSession, payload: dict[str, Any]) -> dict[str, Any]:
    if not session.organization_id:
        raise ValueError("organization must be ready before provider connection")
    input_payload = _input_payload(payload)
    provider_name = str(input_payload.get("provider_name", "google")).strip().lower()
    auth_mode = str(input_payload.get("provider_auth_mode", "api_key")).strip()
    credentials = input_payload.get("provider_credentials") or {}
    if not isinstance(credentials, dict):
        raise ValueError("provider_credentials must be an object")

    existing = (
        db.query(OrganizationProviderCredential)
        .filter(
            OrganizationProviderCredential.organization_id == session.organization_id,
            OrganizationProviderCredential.provider_name == provider_name,
        )
        .first()
    )
    if existing is not None:
        return {"organization_id": session.organization_id, "provider_name": provider_name, "auth_mode": existing.auth_mode}

    row = provider_credentials_service.upsert_organization_provider_credentials(
        db,
        organization_id=session.organization_id,
        provider_name=provider_name,
        auth_mode=auth_mode,
        credentials=credentials,
    )
    return {"organization_id": row.organization_id, "provider_name": row.provider_name, "auth_mode": row.auth_mode}


def _ensure_crawl_started(db: Session, session: OnboardingSession, payload: dict[str, Any]) -> dict[str, Any]:
    if not session.tenant_id or not session.campaign_id:
        raise ValueError("campaign must be ready before crawl start")
    input_payload = _input_payload(payload)
    crawl_type = str(input_payload.get("crawl_type", "deep")).strip()
    seed_url = str(input_payload.get("crawl_seed_url", "")).strip()
    if not seed_url:
        raise ValueError("crawl_seed_url is required")

    run = (
        db.query(CrawlRun)
        .filter(CrawlRun.tenant_id == session.tenant_id, CrawlRun.campaign_id == session.campaign_id)
        .order_by(CrawlRun.created_at.desc())
        .first()
    )
    if run is None:
        run = crawl_service.schedule_crawl(
            db,
            tenant_id=session.tenant_id,
            campaign_id=session.campaign_id,
            crawl_type=crawl_type,
            seed_url=seed_url,
        )

    task_ids = payload.setdefault("task_ids", {})
    if CRAWL_STARTED not in task_ids:
        task_id = _dispatch_crawl_task(db, run)
        task_ids[CRAWL_STARTED] = task_id

    _ensure_campaign_state(db, session.tenant_id, session.campaign_id, target_state="BaselineRunning")
    return {"crawl_run_id": run.id, "status": run.status, "task_id": task_ids.get(CRAWL_STARTED)}


def _ensure_report_generated(db: Session, session: OnboardingSession, payload: dict[str, Any]) -> dict[str, Any]:
    if not session.tenant_id or not session.campaign_id:
        raise ValueError("campaign must be ready before report generation")
    input_payload = _input_payload(payload)
    month_number = int(input_payload.get("report_month_number", 1))

    report = (
        db.query(MonthlyReport)
        .filter(
            MonthlyReport.tenant_id == session.tenant_id,
            MonthlyReport.campaign_id == session.campaign_id,
            MonthlyReport.month_number == month_number,
        )
        .order_by(MonthlyReport.generated_at.desc())
        .first()
    )
    if report is None:
        report = reporting_service.generate_report(
            db,
            tenant_id=session.tenant_id,
            campaign_id=session.campaign_id,
            month_number=month_number,
        )
    return {"report_id": report.id, "month_number": report.month_number, "report_status": report.report_status}


def _ensure_automation_enabled(db: Session, session: OnboardingSession, payload: dict[str, Any]) -> dict[str, Any]:
    if not session.tenant_id or not session.campaign_id:
        raise ValueError("campaign must be ready before automation activation")
    input_payload = _input_payload(payload)
    override = bool(input_payload.get("automation_override", False))

    automation_result = intelligence_service.advance_month(
        db,
        tenant_id=session.tenant_id,
        campaign_id=session.campaign_id,
        override=override,
    )
    _ensure_campaign_state(db, session.tenant_id, session.campaign_id, target_state="Active")
    return automation_result


def _dispatch_crawl_task(db: Session, run: CrawlRun) -> str | None:
    try:
        task = crawl_schedule_campaign.delay(campaign_id=run.campaign_id, crawl_run_id=run.id, tenant_id=run.tenant_id)
        return task.id
    except Exception:
        try:
            crawl_service.execute_run(db, crawl_run_id=run.id)
        except Exception as exc:  # noqa: BLE001
            crawl_service.mark_run_failed(db, run.id, str(exc))
        return None


def _ensure_campaign_state(db: Session, tenant_id: str, campaign_id: str, target_state: str) -> None:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None or campaign.tenant_id != tenant_id:
        raise ValueError("campaign not found")
    ordered = ["Draft", "Configured", "BaselineRunning", "Active"]
    if campaign.setup_state == target_state:
        return
    if campaign.setup_state not in ordered or target_state not in ordered:
        return
    current_idx = ordered.index(campaign.setup_state)
    target_idx = ordered.index(target_state)
    if current_idx > target_idx:
        return
    for idx in range(current_idx + 1, target_idx + 1):
        lifecycle_service.transition_campaign_setup_state(
            db,
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            target_state=ordered[idx],
        )


def _latest_session_by_tenant(db: Session, tenant_id: str) -> OnboardingSession | None:
    return (
        db.query(OnboardingSession)
        .filter(OnboardingSession.tenant_id == tenant_id)
        .order_by(OnboardingSession.created_at.desc())
        .first()
    )


def _idempotency_key(session_id: str, step: str) -> str:
    return f"onboarding:{session_id}:{step}"


def _mark_step_completed(payload: dict[str, Any], step: str, result: dict[str, Any]) -> None:
    completed_steps = payload.setdefault("completed_steps", [])
    if step not in completed_steps:
        completed_steps.append(step)
    step_results = payload.setdefault("step_results", {})
    step_results[step] = result


def _store_idempotency_key(payload: dict[str, Any], step: str, key: str) -> None:
    payload.setdefault("idempotency_keys", {})[step] = key


def _session_payload(session: OnboardingSession) -> dict[str, Any]:
    if isinstance(session.step_payload, dict):
        return dict(session.step_payload)
    return {"input": {}, "completed_steps": [], "idempotency_keys": {}, "step_results": {}, "task_ids": {}}


def _input_payload(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("input")
    return value if isinstance(value, dict) else {}


def _resume_from_state(session: OnboardingSession) -> str:
    if isinstance(session.error_state, dict):
        resume_from = session.error_state.get("resume_from")
        if isinstance(resume_from, str) and resume_from in STATE_SEQUENCE:
            return resume_from
    return INITIALIZED


def _last_non_failed_step(current_step: str, error_state: dict | None) -> str:
    if current_step in STATE_SEQUENCE:
        return current_step
    if isinstance(error_state, dict):
        resume_from = error_state.get("resume_from")
        if isinstance(resume_from, str) and resume_from in STATE_SEQUENCE:
            return resume_from
    return INITIALIZED
