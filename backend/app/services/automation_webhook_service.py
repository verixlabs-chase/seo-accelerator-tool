from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import json
import re
import time
from typing import Any
from urllib.parse import urlsplit, urlunsplit
import uuid

import httpx
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.automation import (
    AUTOMATION_EVENT_SCHEMA_VERSION,
    AUTOMATION_PROVIDER_SETUP_VERSION,
    AUTOMATION_RECIPE_CATALOG_VERSION,
    AutomationEventEnvelope,
    automation_event_catalog,
    automation_provider_setup_catalog,
    automation_starter_recipe_catalog,
    build_automation_event,
    generate_signing_secret,
    sign_automation_event,
)
from app.core.config import get_settings
from app.core.crypto import CredentialCryptoError, decrypt_payload, encrypt_payload
from app.events.emitter import EventEnvelope
from app.events.outbox.event_outbox import EventOutbox
from app.models.automation_webhook import (
    AutomationWebhookConnection,
    AutomationWebhookDelivery,
    AutomationWebhookDeliveryAttempt,
)
from app.models.campaign import Campaign
from app.models.intelligence import StrategyRecommendation
from app.models.organization import Organization
from app.models.platform_job import PlatformJob
from app.models.recommendation_execution import RecommendationExecution
from app.models.reporting import MonthlyReport
from app.services.audit_service import write_audit_log
from app.services.commercial_plan_service import (
    FEATURE_EXTERNAL_AUTOMATION,
    CostEconomicsError,
    require_commercial_feature,
)
from app.services import job_service


AUTOMATION_DELIVERY_TIMEOUT_SECONDS = 10.0
AUTOMATION_DELIVERY_MAX_ATTEMPTS = 3
AUTOMATION_FANOUT_JOB_TYPE = "automation.webhook.fanout"
AUTOMATION_DELIVERY_JOB_TYPE = "automation.webhook.deliver"
_PROVIDERS = {
    "zapier": "Zapier",
    "make": "Make",
    "pipedream": "Pipedream",
    "n8n": "n8n Cloud",
}
_PIPEDREAM_HOST = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}\.m\.pipedream\.net$")
_MAKE_HOST = re.compile(r"^hook(?:\.[a-z0-9-]+)?\.make\.com$")
_N8N_CLOUD_HOST = re.compile(
    r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.app\.n8n\.cloud$"
)
_PRODUCT_EVENT_TYPES = {
    "report.generated": "report.ready",
    "report.regenerated": "report.ready",
    "onboarding.baseline_generated": "report.ready",
    "recommendation.generated": "recommendation.ready",
    "execution.completed": "action.completed",
    "execution.failed": "action.failed",
}
_LIVE_SUBSCRIPTION_TYPES = frozenset(_PRODUCT_EVENT_TYPES.values())


class AutomationWebhookError(RuntimeError):
    def __init__(self, message: str, *, reason_code: str, status_code: int = 409) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.status_code = status_code


class AutomationDeliveryRetryableError(RuntimeError):
    """Safe durable-job signal after one persisted delivery failure."""


def list_connections(db: Session, *, organization_id: str) -> dict[str, Any]:
    rows = (
        db.query(AutomationWebhookConnection)
        .filter(AutomationWebhookConnection.organization_id == organization_id)
        .order_by(AutomationWebhookConnection.created_at.asc())
        .all()
    )
    return {
        "items": [_serialize_connection(db, row) for row in rows],
        "supported_providers": [
            {"code": code, "label": label} for code, label in _PROVIDERS.items()
        ],
        "supported_events": [
            item
            for item in automation_event_catalog()
            if item["code"] in _LIVE_SUBSCRIPTION_TYPES
        ],
        "contract_events": automation_event_catalog(),
        "live_event_types": sorted(set(_PRODUCT_EVENT_TYPES.values())),
        "recipe_catalog_version": AUTOMATION_RECIPE_CATALOG_VERSION,
        "starter_recipes": automation_starter_recipe_catalog(
            live_event_types=_LIVE_SUBSCRIPTION_TYPES
        ),
        "provider_setup_version": AUTOMATION_PROVIDER_SETUP_VERSION,
        "provider_setup": automation_provider_setup_catalog(
            supported_provider_codes=frozenset(_PROVIDERS)
        ),
        "automatic_actions_enabled": False,
        "truth": (
            "Approved product events are delivered as signed outbound notifications. "
            "Connected tools cannot approve, publish, change a website, or change a "
            "business profile."
        ),
    }


def queue_fanout_for_outbox_event(db: Session, *, event: EventEnvelope) -> bool:
    """Create one durable fanout job for a committed, approved product event."""
    if event.event_type not in _PRODUCT_EVENT_TYPES:
        return False
    job_service.create_job(
        db,
        tenant_id=event.tenant_id,
        job_type=AUTOMATION_FANOUT_JOB_TYPE,
        entity_type="event_outbox",
        entity_id=event.event_id,
        idempotency_key=f"{AUTOMATION_FANOUT_JOB_TYPE}:{event.event_id}",
        payload={
            "tenant_id": event.tenant_id,
            "source_outbox_event_id": event.event_id,
        },
        max_retries=2,
    )
    return True


def fan_out_product_event(
    db: Session,
    *,
    organization_id: str,
    source_outbox_event_id: str,
) -> dict[str, Any]:
    source = (
        db.query(EventOutbox)
        .filter(
            EventOutbox.id == source_outbox_event_id,
            EventOutbox.tenant_id == organization_id,
        )
        .one_or_none()
    )
    if source is None:
        raise AutomationWebhookError(
            "The product event is no longer available for delivery.",
            reason_code="automation_source_event_not_found",
            status_code=404,
        )
    internal = EventEnvelope.model_validate_json(source.payload_json)
    external = _translate_product_event(db, source=source, event=internal)
    if external is None:
        return {
            "source_event_id": source.id,
            "event_type": None,
            "connections_matched": 0,
            "deliveries_created": 0,
            "deliveries_existing": 0,
        }

    connections = (
        db.query(AutomationWebhookConnection)
        .filter(
            AutomationWebhookConnection.organization_id == organization_id,
            AutomationWebhookConnection.status == "active",
            AutomationWebhookConnection.verification_status == "verified",
        )
        .order_by(AutomationWebhookConnection.id.asc())
        .all()
    )
    matched = [
        row for row in connections if external.event_type in _event_types(row.event_types_json)
    ]
    created = 0
    existing = 0
    for connection in matched:
        delivery = (
            db.query(AutomationWebhookDelivery)
            .filter(
                AutomationWebhookDelivery.connection_id == connection.id,
                AutomationWebhookDelivery.event_id == external.event_id,
            )
            .one_or_none()
        )
        if delivery is not None:
            existing += 1
            continue
        delivery = _new_delivery(
            connection=connection,
            event=external,
            delivery_kind="product",
            source_outbox_event_id=source.id,
            actor_user_id=None,
        )
        db.add(delivery)
        db.flush()
        job = _queue_delivery_job(db, delivery=delivery)
        delivery.platform_job_id = job.id
        write_audit_log(
            db,
            tenant_id=organization_id,
            actor_user_id=None,
            event_type="automation.webhook_delivery.queued",
            payload={
                "connection_id": connection.id,
                "delivery_id": delivery.id,
                "event_id": delivery.event_id,
                "event_type": delivery.event_type,
                "delivery_kind": delivery.delivery_kind,
            },
        )
        created += 1
    db.flush()
    return {
        "source_event_id": source.id,
        "event_type": external.event_type,
        "connections_matched": len(matched),
        "deliveries_created": created,
        "deliveries_existing": existing,
    }


def run_background_delivery(
    db: Session,
    *,
    organization_id: str,
    delivery_id: str,
) -> dict[str, Any]:
    result = _attempt_delivery(
        db,
        organization_id=organization_id,
        delivery_id=delivery_id,
        actor_user_id=None,
    )
    delivery = result["delivery"]
    if delivery["status"] == "failed":
        raise AutomationDeliveryRetryableError(
            "The workflow endpoint did not accept this signed event."
        )
    return {
        "delivery_id": delivery["id"],
        "event_id": delivery["event_id"],
        "status": delivery["status"],
        "attempt_count": delivery["attempt_count"],
    }


def create_connection(
    db: Session,
    *,
    organization_id: str,
    actor_user_id: str,
    name: str,
    provider: str,
    destination_url: str,
    event_types: list[str],
) -> dict[str, Any]:
    organization = _locked_organization(db, organization_id)
    _require_feature(db, organization_id)
    normalized_name = " ".join(str(name or "").split())
    if not 2 <= len(normalized_name) <= 120:
        raise AutomationWebhookError(
            "Give this connection a name between 2 and 120 characters.",
            reason_code="automation_connection_name_invalid",
            status_code=422,
        )
    normalized_provider = str(provider or "").strip().lower()
    destination, endpoint_host = validate_automation_destination(
        provider=normalized_provider,
        destination_url=destination_url,
    )
    approved_events = _validate_event_types(event_types)
    existing = (
        db.query(AutomationWebhookConnection.id)
        .filter(
            AutomationWebhookConnection.organization_id == organization_id,
            AutomationWebhookConnection.name == normalized_name,
        )
        .first()
    )
    if existing is not None:
        raise AutomationWebhookError(
            "A connection with this name already exists.",
            reason_code="automation_connection_name_exists",
        )

    signing_secret = generate_signing_secret()
    encrypted_blob, key_reference, key_version = _encrypt_config(
        {"destination_url": destination, "signing_secret": signing_secret}
    )
    now = datetime.now(UTC)
    row = AutomationWebhookConnection(
        id=str(uuid.uuid4()),
        tenant_id=organization.id,
        organization_id=organization.id,
        name=normalized_name,
        provider=normalized_provider,
        status="pending",
        endpoint_host=endpoint_host,
        event_types_json=json.dumps(approved_events, separators=(",", ":")),
        encrypted_config_blob=encrypted_blob,
        key_reference=key_reference,
        key_version=key_version,
        signing_secret_version=1,
        verification_status="not_tested",
        consecutive_failures=0,
        created_by_user_id=actor_user_id,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    write_audit_log(
        db,
        tenant_id=organization.id,
        actor_user_id=actor_user_id,
        event_type="automation.webhook_connection.created",
        payload={
            "connection_id": row.id,
            "provider": row.provider,
            "endpoint_host": row.endpoint_host,
            "event_types": approved_events,
        },
    )
    db.commit()
    db.refresh(row)
    return {
        "connection": _serialize_connection(db, row),
        "signing_secret": signing_secret,
        "secret_shown_once": True,
        "next_step": "Save the signing secret, then send a test event.",
    }


def rotate_signing_secret(
    db: Session,
    *,
    organization_id: str,
    connection_id: str,
    actor_user_id: str,
) -> dict[str, Any]:
    row = _locked_connection(db, organization_id=organization_id, connection_id=connection_id)
    _require_connected_config(row)
    config = _decrypt_config(row.encrypted_config_blob)
    signing_secret = generate_signing_secret()
    encrypted_blob, key_reference, key_version = _encrypt_config(
        {
            "destination_url": str(config["destination_url"]),
            "signing_secret": signing_secret,
        }
    )
    now = datetime.now(UTC)
    row.encrypted_config_blob = encrypted_blob
    row.key_reference = key_reference
    row.key_version = key_version
    row.signing_secret_version += 1
    row.status = "pending"
    row.verification_status = "not_tested"
    row.paused_by_user_id = None
    row.paused_at = None
    row.updated_at = now
    write_audit_log(
        db,
        tenant_id=organization_id,
        actor_user_id=actor_user_id,
        event_type="automation.webhook_connection.secret_rotated",
        payload={
            "connection_id": row.id,
            "provider": row.provider,
            "signing_secret_version": row.signing_secret_version,
        },
    )
    db.commit()
    db.refresh(row)
    return {
        "connection": _serialize_connection(db, row),
        "signing_secret": signing_secret,
        "secret_shown_once": True,
        "next_step": "Replace the old secret in your workflow, then send a new test event.",
    }


def pause_connection(
    db: Session,
    *,
    organization_id: str,
    connection_id: str,
    actor_user_id: str,
) -> dict[str, Any]:
    row = _locked_connection(
        db, organization_id=organization_id, connection_id=connection_id
    )
    _require_connected_config(row)
    if row.status != "paused":
        now = datetime.now(UTC)
        row.status = "paused"
        row.paused_by_user_id = actor_user_id
        row.paused_at = now
        row.updated_at = now
        write_audit_log(
            db,
            tenant_id=organization_id,
            actor_user_id=actor_user_id,
            event_type="automation.webhook_connection.paused",
            payload={"connection_id": row.id, "provider": row.provider},
        )
        db.commit()
        db.refresh(row)
    return {
        "connection": _serialize_connection(db, row),
        "new_product_deliveries_enabled": False,
    }


def resume_connection(
    db: Session,
    *,
    organization_id: str,
    connection_id: str,
    actor_user_id: str,
) -> dict[str, Any]:
    row = _locked_connection(
        db, organization_id=organization_id, connection_id=connection_id
    )
    _require_connected_config(row)
    if row.status == "paused":
        now = datetime.now(UTC)
        row.status = "active" if row.verification_status == "verified" else "pending"
        row.paused_by_user_id = None
        row.paused_at = None
        row.updated_at = now
        write_audit_log(
            db,
            tenant_id=organization_id,
            actor_user_id=actor_user_id,
            event_type="automation.webhook_connection.resumed",
            payload={"connection_id": row.id, "provider": row.provider},
        )
        db.commit()
        db.refresh(row)
    return {
        "connection": _serialize_connection(db, row),
        "new_product_deliveries_enabled": row.status == "active",
    }


def disconnect_connection(
    db: Session,
    *,
    organization_id: str,
    connection_id: str,
    actor_user_id: str,
) -> dict[str, Any]:
    row = _locked_connection(db, organization_id=organization_id, connection_id=connection_id)
    now = datetime.now(UTC)
    if row.status != "disconnected":
        row.status = "disconnected"
        row.verification_status = "not_tested"
        row.encrypted_config_blob = None
        row.key_reference = None
        row.key_version = None
        row.paused_by_user_id = None
        row.paused_at = None
        row.disconnected_by_user_id = actor_user_id
        row.disconnected_at = now
        row.updated_at = now
        write_audit_log(
            db,
            tenant_id=organization_id,
            actor_user_id=actor_user_id,
            event_type="automation.webhook_connection.disconnected",
            payload={"connection_id": row.id, "provider": row.provider},
        )
        db.commit()
        db.refresh(row)
    return {"connection": _serialize_connection(db, row), "secrets_removed": True}


def recover_dead_letter_delivery(
    db: Session,
    *,
    organization_id: str,
    delivery_id: str,
    actor_user_id: str,
) -> dict[str, Any]:
    delivery = (
        db.query(AutomationWebhookDelivery)
        .filter(
            AutomationWebhookDelivery.id == delivery_id,
            AutomationWebhookDelivery.organization_id == organization_id,
        )
        .populate_existing()
        .with_for_update()
        .one_or_none()
    )
    if delivery is None:
        raise AutomationWebhookError(
            "Automation delivery not found.",
            reason_code="automation_delivery_not_found",
            status_code=404,
        )
    if delivery.status != "dead_letter":
        raise AutomationWebhookError(
            "Only a delivery that exhausted its attempts can be recovered.",
            reason_code="automation_delivery_recovery_unavailable",
        )
    connection = _locked_connection(
        db,
        organization_id=organization_id,
        connection_id=delivery.connection_id,
    )
    _require_connected_config(connection)
    if connection.status == "paused":
        raise AutomationWebhookError(
            "Resume this workflow connection before recovering the event.",
            reason_code="automation_connection_paused",
        )
    now = datetime.now(UTC)
    delivery.recovery_count += 1
    delivery.max_attempts += AUTOMATION_DELIVERY_MAX_ATTEMPTS
    delivery.status = "pending"
    delivery.dead_lettered_at = None
    delivery.next_attempt_at = now
    delivery.updated_at = now
    job = _queue_delivery_job(db, delivery=delivery)
    delivery.platform_job_id = job.id
    write_audit_log(
        db,
        tenant_id=organization_id,
        actor_user_id=actor_user_id,
        event_type="automation.webhook_delivery.recovered",
        payload={
            "connection_id": delivery.connection_id,
            "delivery_id": delivery.id,
            "event_id": delivery.event_id,
            "recovery_count": delivery.recovery_count,
        },
    )
    db.commit()
    db.refresh(delivery)
    return {
        "delivery": _serialize_delivery(db, delivery),
        "queued": True,
        "automatic_actions_enabled": False,
    }


def send_test_delivery(
    db: Session,
    *,
    organization_id: str,
    connection_id: str,
    actor_user_id: str,
) -> dict[str, Any]:
    row = _locked_connection(db, organization_id=organization_id, connection_id=connection_id)
    _require_feature(db, organization_id)
    _require_connected_config(row)
    if row.status == "paused":
        raise AutomationWebhookError(
            "Resume this workflow connection before sending a test.",
            reason_code="automation_connection_paused",
        )
    now = datetime.now(UTC)
    event = build_automation_event(
        event_id=f"evt_automation_test_{uuid.uuid4().hex}",
        event_type="connection.health_changed",
        occurred_at=now,
        organization_id=organization_id,
        location_id=None,
        truth_state="in_progress",
        resource_type="connection",
        resource_id=row.id,
        resource_href="/settings#external-automation",
        data={
            "connection_name": row.name,
            "state": "test",
            "summary": "InsightOS sent this signed test event to verify the connection.",
            "recovery_href": "/settings#external-automation",
        },
    )
    delivery = _new_delivery(
        connection=row,
        event=event,
        delivery_kind="test",
        source_outbox_event_id=None,
        actor_user_id=actor_user_id,
    )
    db.add(delivery)
    write_audit_log(
        db,
        tenant_id=organization_id,
        actor_user_id=actor_user_id,
        event_type="automation.webhook_delivery.created",
        payload={
            "connection_id": row.id,
            "delivery_id": delivery.id,
            "event_id": delivery.event_id,
            "event_type": delivery.event_type,
        },
    )
    db.commit()
    return _attempt_delivery(
        db,
        organization_id=organization_id,
        delivery_id=delivery.id,
        actor_user_id=actor_user_id,
    )


def retry_delivery(
    db: Session,
    *,
    organization_id: str,
    delivery_id: str,
    actor_user_id: str,
) -> dict[str, Any]:
    return _attempt_delivery(
        db,
        organization_id=organization_id,
        delivery_id=delivery_id,
        actor_user_id=actor_user_id,
        retry=True,
    )


def list_deliveries(
    db: Session,
    *,
    organization_id: str,
    connection_id: str | None = None,
) -> dict[str, Any]:
    query = db.query(AutomationWebhookDelivery).filter(
        AutomationWebhookDelivery.organization_id == organization_id
    )
    if connection_id:
        query = query.filter(AutomationWebhookDelivery.connection_id == connection_id)
    rows = query.order_by(AutomationWebhookDelivery.created_at.desc()).limit(50).all()
    return {"items": [_serialize_delivery(db, row) for row in rows]}


def validate_automation_destination(*, provider: str, destination_url: str) -> tuple[str, str]:
    if provider not in _PROVIDERS:
        raise AutomationWebhookError(
            "Choose Zapier, Make, Pipedream, or n8n Cloud.",
            reason_code="automation_provider_not_supported",
            status_code=422,
        )
    raw = str(destination_url or "").strip()
    if not raw or len(raw) > 2_000 or any(character.isspace() for character in raw):
        raise _destination_error()
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError as exc:
        raise _destination_error() from exc
    host = str(parsed.hostname or "").lower().rstrip(".")
    if (
        parsed.scheme.lower() != "https"
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or port not in {None, 443}
    ):
        raise _destination_error()
    if provider in {"zapier", "make"} and parsed.path in {"", "/"}:
        raise _destination_error()
    valid = False
    if provider == "zapier":
        valid = host == "hooks.zapier.com" and parsed.path.startswith("/hooks/catch/")
    elif provider == "make":
        valid = _MAKE_HOST.fullmatch(host) is not None and parsed.path not in {"", "/"}
    elif provider == "pipedream":
        valid = _PIPEDREAM_HOST.fullmatch(host) is not None
    elif provider == "n8n":
        valid = (
            _N8N_CLOUD_HOST.fullmatch(host) is not None
            and parsed.path.startswith("/webhook/")
            and len(parsed.path) > len("/webhook/")
        )
    if not valid:
        raise AutomationWebhookError(
            f"This is not a supported {_PROVIDERS[provider]} webhook URL.",
            reason_code="automation_destination_provider_mismatch",
            status_code=422,
        )
    canonical = urlunsplit(("https", host, parsed.path, parsed.query, ""))
    return canonical, host


def _new_delivery(
    *,
    connection: AutomationWebhookConnection,
    event: AutomationEventEnvelope,
    delivery_kind: str,
    source_outbox_event_id: str | None,
    actor_user_id: str | None,
) -> AutomationWebhookDelivery:
    event_json = event.model_dump(mode="json")
    encrypted_event_blob, _, _ = _encrypt_config({"event": event_json})
    event_bytes = json.dumps(
        event_json, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    now = datetime.now(UTC)
    return AutomationWebhookDelivery(
        id=str(uuid.uuid4()),
        tenant_id=connection.tenant_id,
        organization_id=connection.organization_id,
        connection_id=connection.id,
        event_id=event.event_id,
        event_type=event.event_type,
        schema_version=AUTOMATION_EVENT_SCHEMA_VERSION,
        status="pending",
        delivery_kind=delivery_kind,
        source_outbox_event_id=source_outbox_event_id,
        encrypted_event_blob=encrypted_event_blob,
        event_hash=hashlib.sha256(event_bytes).hexdigest(),
        attempt_count=0,
        max_attempts=AUTOMATION_DELIVERY_MAX_ATTEMPTS,
        recovery_count=0,
        created_by_user_id=actor_user_id,
        next_attempt_at=now if delivery_kind == "product" else None,
        created_at=now,
        updated_at=now,
    )


def _queue_delivery_job(
    db: Session,
    *,
    delivery: AutomationWebhookDelivery,
) -> PlatformJob:
    return job_service.create_job(
        db,
        tenant_id=delivery.organization_id,
        job_type=AUTOMATION_DELIVERY_JOB_TYPE,
        entity_type="automation_webhook_delivery",
        entity_id=delivery.id,
        idempotency_key=(
            f"{AUTOMATION_DELIVERY_JOB_TYPE}:{delivery.id}:"
            f"recovery:{delivery.recovery_count}"
        ),
        payload={
            "tenant_id": delivery.organization_id,
            "delivery_id": delivery.id,
            "recovery_count": delivery.recovery_count,
        },
        available_at=delivery.next_attempt_at or datetime.now(UTC),
        max_retries=2,
    )


def _translate_product_event(
    db: Session,
    *,
    source: EventOutbox,
    event: EventEnvelope,
) -> AutomationEventEnvelope | None:
    external_type = _PRODUCT_EVENT_TYPES.get(event.event_type)
    if external_type is None or event.tenant_id != source.tenant_id:
        return None
    payload = dict(event.payload or {})
    occurred_at = _event_timestamp(event.timestamp)
    external_event_id = f"evt_product_{source.id.replace('-', '')}"
    campaign_id = str(payload.get("campaign_id") or "").strip()

    if external_type == "report.ready":
        report_id = str(payload.get("report_id") or "").strip()
        report = db.get(MonthlyReport, report_id) if report_id else None
        campaign = db.get(Campaign, campaign_id) if campaign_id else None
        if (
            report is None
            or campaign is None
            or report.tenant_id != source.tenant_id
            or report.campaign_id != campaign.id
            or campaign.tenant_id != source.tenant_id
        ):
            return None
        return build_automation_event(
            event_id=external_event_id,
            event_type=external_type,
            occurred_at=occurred_at,
            organization_id=source.tenant_id,
            location_id=campaign.business_location_id,
            truth_state="ready",
            resource_type="report",
            resource_id=report.id,
            resource_href="/reports",
            data={
                "report_id": report.id,
                "report_label": f"{campaign.name} report",
                "observed_through": _iso(report.generated_at),
                "summary": "A saved InsightOS report is ready for owner review.",
                "report_href": "/reports",
            },
        )

    if external_type == "recommendation.ready":
        recommendation_id = str(payload.get("recommendation_id") or "").strip()
        recommendation = (
            db.get(StrategyRecommendation, recommendation_id)
            if recommendation_id
            else None
        )
        campaign = db.get(Campaign, campaign_id) if campaign_id else None
        if (
            recommendation is None
            or campaign is None
            or recommendation.tenant_id != source.tenant_id
            or recommendation.campaign_id != campaign.id
            or campaign.tenant_id != source.tenant_id
        ):
            return None
        priority = "Higher attention" if int(recommendation.risk_tier or 0) >= 3 else "Standard"
        return build_automation_event(
            event_id=external_event_id,
            event_type=external_type,
            occurred_at=occurred_at,
            organization_id=source.tenant_id,
            location_id=campaign.business_location_id,
            truth_state="ready",
            resource_type="recommendation",
            resource_id=recommendation.id,
            resource_href="/opportunities",
            data={
                "recommendation_id": recommendation.id,
                "title": "Review a new SEO recommendation",
                "priority": priority,
                "summary": "A saved, evidence-backed recommendation is ready for owner review.",
                "recommendation_href": "/opportunities",
            },
        )

    execution_id = str(payload.get("execution_id") or "").strip()
    execution = db.get(RecommendationExecution, execution_id) if execution_id else None
    campaign = db.get(Campaign, campaign_id) if campaign_id else None
    if (
        execution is None
        or campaign is None
        or execution.campaign_id != campaign.id
        or campaign.tenant_id != source.tenant_id
    ):
        return None
    if external_type == "action.completed":
        return build_automation_event(
            event_id=external_event_id,
            event_type=external_type,
            occurred_at=occurred_at,
            organization_id=source.tenant_id,
            location_id=campaign.business_location_id,
            truth_state="completed",
            resource_type="action",
            resource_id=execution.id,
            resource_href="/opportunities",
            data={
                "action_id": execution.id,
                "title": "Approved SEO action",
                "completed_at": _iso(execution.executed_at) or occurred_at.isoformat(),
                "result_summary": "The approved action finished and saved its result.",
                "action_href": "/opportunities",
            },
        )
    if external_type == "action.failed":
        return build_automation_event(
            event_id=external_event_id,
            event_type=external_type,
            occurred_at=occurred_at,
            organization_id=source.tenant_id,
            location_id=campaign.business_location_id,
            truth_state="failed",
            resource_type="action",
            resource_id=execution.id,
            resource_href="/opportunities",
            data={
                "action_id": execution.id,
                "title": "Approved SEO action needs attention",
                "failed_at": occurred_at.isoformat(),
                "summary": "The approved action stopped and saved recovery guidance.",
                "recovery": "Open InsightOS to review the saved failure before trying again.",
                "action_href": "/opportunities",
            },
        )
    return None


def _event_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise AutomationWebhookError(
            "The product event timestamp is invalid.",
            reason_code="automation_source_event_invalid",
        ) from exc
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _attempt_delivery(
    db: Session,
    *,
    organization_id: str,
    delivery_id: str,
    actor_user_id: str | None,
    retry: bool = False,
) -> dict[str, Any]:
    delivery = (
        db.query(AutomationWebhookDelivery)
        .filter(
            AutomationWebhookDelivery.id == delivery_id,
            AutomationWebhookDelivery.organization_id == organization_id,
        )
        .populate_existing()
        .with_for_update()
        .first()
    )
    if delivery is None:
        raise AutomationWebhookError(
            "Automation delivery not found.",
            reason_code="automation_delivery_not_found",
            status_code=404,
        )
    if delivery.status == "delivered":
        if retry:
            raise AutomationWebhookError(
                "This event was already delivered and will not be sent twice.",
                reason_code="automation_delivery_already_delivered",
            )
        return {"delivery": _serialize_delivery(db, delivery)}
    if delivery.status in {"dead_letter", "cancelled"}:
        if retry:
            raise AutomationWebhookError(
                "This delivery needs owner recovery before it can be sent again.",
                reason_code="automation_delivery_recovery_required",
            )
        return {
            "delivery": _serialize_delivery(db, delivery),
            "received_by_destination": False,
        }
    recoverable_pending = delivery.status == "pending" and delivery.attempt_count == 0
    if retry and delivery.status != "failed" and not recoverable_pending:
        raise AutomationWebhookError(
            "Only a failed or interrupted delivery can be retried.",
            reason_code="automation_delivery_not_retryable",
        )
    if delivery.attempt_count >= delivery.max_attempts:
        raise AutomationWebhookError(
            "This delivery reached its retry limit. Create a new test after checking the workflow.",
            reason_code="automation_delivery_retry_limit",
        )
    connection = _locked_connection(
        db,
        organization_id=organization_id,
        connection_id=delivery.connection_id,
    )
    if connection.status == "disconnected" or not connection.encrypted_config_blob:
        if delivery.delivery_kind == "product":
            return _cancel_undispatched_delivery(
                db,
                delivery=delivery,
                connection=connection,
                actor_user_id=actor_user_id,
                reason_code="automation_connection_disconnected",
            )
        _require_connected_config(connection)
    try:
        _require_feature(db, organization_id)
    except AutomationWebhookError as exc:
        if delivery.delivery_kind == "product":
            return _cancel_undispatched_delivery(
                db,
                delivery=delivery,
                connection=connection,
                actor_user_id=actor_user_id,
                reason_code=exc.reason_code,
            )
        raise
    if connection.status == "paused":
        return _cancel_undispatched_delivery(
            db,
            delivery=delivery,
            connection=connection,
            actor_user_id=actor_user_id,
            reason_code="automation_connection_paused",
        )
    _require_connected_config(connection)
    try:
        config = _decrypt_config(connection.encrypted_config_blob)
        destination, host = validate_automation_destination(
            provider=connection.provider,
            destination_url=str(config.get("destination_url") or ""),
        )
        if host != connection.endpoint_host:
            raise AutomationWebhookError(
                "The saved destination no longer matches this connection.",
                reason_code="automation_destination_identity_mismatch",
            )
        event_payload = _decrypt_config(delivery.encrypted_event_blob).get("event")
        event = AutomationEventEnvelope.model_validate(event_payload)
    except (CredentialCryptoError, ValidationError, TypeError, ValueError) as exc:
        error = AutomationWebhookError(
            "The saved event cannot be delivered safely.",
            reason_code="automation_delivery_event_invalid",
        )
        if delivery.delivery_kind == "product":
            return _cancel_undispatched_delivery(
                db,
                delivery=delivery,
                connection=connection,
                actor_user_id=actor_user_id,
                reason_code=error.reason_code,
            )
        raise error from exc
    except AutomationWebhookError as exc:
        if delivery.delivery_kind == "product":
            return _cancel_undispatched_delivery(
                db,
                delivery=delivery,
                connection=connection,
                actor_user_id=actor_user_id,
                reason_code=exc.reason_code,
            )
        raise
    signed = sign_automation_event(
        event,
        signing_secret=str(config.get("signing_secret") or ""),
    )
    attempt_number = delivery.attempt_count + 1
    attempted_at = datetime.now(UTC)
    delivery.attempt_count = attempt_number
    delivery.status = "pending"
    delivery.last_attempt_at = attempted_at
    delivery.next_attempt_at = None
    delivery.updated_at = attempted_at
    db.flush()

    started = time.monotonic()
    response_status: int | None = None
    reason_code: str | None = None
    delivered = False
    try:
        response_status = _post_signed_event(
            destination_url=destination,
            body=signed.body,
            headers=signed.headers,
        )
        delivered = 200 <= response_status < 300
        if not delivered:
            reason_code = "automation_destination_rejected"
    except (httpx.TimeoutException, httpx.NetworkError):
        reason_code = "automation_destination_unreachable"
    except httpx.HTTPError:
        reason_code = "automation_delivery_failed"
    duration_ms = max(0, int((time.monotonic() - started) * 1_000))
    now = datetime.now(UTC)
    attempt = AutomationWebhookDeliveryAttempt(
        id=str(uuid.uuid4()),
        tenant_id=delivery.tenant_id,
        organization_id=delivery.organization_id,
        delivery_id=delivery.id,
        attempt_number=attempt_number,
        status="delivered" if delivered else "failed",
        response_status=response_status,
        reason_code=reason_code,
        duration_ms=duration_ms,
        attempted_at=now,
    )
    db.add(attempt)
    exhausted = not delivered and attempt_number >= delivery.max_attempts
    delivery.status = "delivered" if delivered else "dead_letter" if exhausted else "failed"
    delivery.last_reason_code = reason_code
    delivery.last_response_status = response_status
    delivery.delivered_at = now if delivered else None
    delivery.dead_lettered_at = now if exhausted else None
    if not delivered and not exhausted:
        retry_base = max(1, int(get_settings().durable_job_retry_base_seconds))
        delay_seconds = min(3600, retry_base * (2 ** max(0, attempt_number - 1)))
        delivery.next_attempt_at = now + timedelta(seconds=delay_seconds)
    delivery.updated_at = now
    if delivery.delivery_kind == "test":
        connection.last_tested_at = now
    connection.updated_at = now
    if delivered:
        connection.status = "active"
        connection.verification_status = "verified"
        connection.consecutive_failures = 0
        connection.last_success_at = now
    else:
        connection.status = "unhealthy"
        if delivery.delivery_kind == "test":
            connection.verification_status = "failed"
        connection.consecutive_failures += 1
        connection.last_failure_at = now
    write_audit_log(
        db,
        tenant_id=organization_id,
        actor_user_id=actor_user_id,
        event_type=(
            "automation.webhook_delivery.delivered"
            if delivered
            else "automation.webhook_delivery.failed"
        ),
        payload={
            "connection_id": connection.id,
            "delivery_id": delivery.id,
            "event_id": delivery.event_id,
            "attempt_number": attempt_number,
            "response_status": response_status,
            "reason_code": reason_code,
        },
    )
    db.commit()
    db.refresh(delivery)
    return {
        "delivery": _serialize_delivery(db, delivery),
        "connection": _serialize_connection(db, connection),
        "received_by_destination": delivered,
    }


def _cancel_undispatched_delivery(
    db: Session,
    *,
    delivery: AutomationWebhookDelivery,
    connection: AutomationWebhookConnection,
    actor_user_id: str | None,
    reason_code: str,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    delivery.status = "cancelled"
    delivery.last_reason_code = reason_code
    delivery.cancelled_at = now
    delivery.next_attempt_at = None
    delivery.updated_at = now
    write_audit_log(
        db,
        tenant_id=delivery.organization_id,
        actor_user_id=actor_user_id,
        event_type="automation.webhook_delivery.cancelled",
        payload={
            "connection_id": connection.id,
            "delivery_id": delivery.id,
            "event_id": delivery.event_id,
            "reason_code": reason_code,
        },
    )
    db.commit()
    db.refresh(delivery)
    return {
        "delivery": _serialize_delivery(db, delivery),
        "connection": _serialize_connection(db, connection),
        "received_by_destination": False,
    }


def _post_signed_event(
    *,
    destination_url: str,
    body: bytes,
    headers: dict[str, str],
) -> int:
    with httpx.Client(
        timeout=AUTOMATION_DELIVERY_TIMEOUT_SECONDS,
        follow_redirects=False,
    ) as client:
        response = client.post(destination_url, content=body, headers=headers)
    return int(response.status_code)


def _serialize_connection(
    db: Session, row: AutomationWebhookConnection
) -> dict[str, Any]:
    last_delivery = (
        db.query(AutomationWebhookDelivery)
        .filter(AutomationWebhookDelivery.connection_id == row.id)
        .order_by(AutomationWebhookDelivery.created_at.desc())
        .first()
    )
    dead_letter_count = (
        db.query(AutomationWebhookDelivery)
        .filter(
            AutomationWebhookDelivery.connection_id == row.id,
            AutomationWebhookDelivery.status == "dead_letter",
        )
        .count()
    )
    recoverable_deliveries = (
        db.query(AutomationWebhookDelivery)
        .filter(
            AutomationWebhookDelivery.connection_id == row.id,
            AutomationWebhookDelivery.status == "dead_letter",
        )
        .order_by(AutomationWebhookDelivery.dead_lettered_at.desc())
        .limit(5)
        .all()
    )
    accepted_product_delivery = None
    if row.verification_status == "verified" and row.last_tested_at is not None:
        accepted_product_delivery = (
            db.query(AutomationWebhookDelivery)
            .filter(
                AutomationWebhookDelivery.connection_id == row.id,
                AutomationWebhookDelivery.delivery_kind == "product",
                AutomationWebhookDelivery.status == "delivered",
                AutomationWebhookDelivery.delivered_at >= row.last_tested_at,
            )
            .order_by(AutomationWebhookDelivery.delivered_at.desc())
            .first()
        )
    conformance_proof = _connection_conformance_proof(
        row=row,
        accepted_product_delivery=accepted_product_delivery,
    )
    return {
        "id": row.id,
        "name": row.name,
        "provider": row.provider,
        "provider_label": _PROVIDERS.get(row.provider, "Automation tool"),
        "status": row.status,
        "endpoint_host": row.endpoint_host,
        "event_types": _event_types(row.event_types_json),
        "verification_status": row.verification_status,
        "signing_secret_version": row.signing_secret_version,
        "last_tested_at": _iso(row.last_tested_at),
        "last_success_at": _iso(row.last_success_at),
        "last_failure_at": _iso(row.last_failure_at),
        "paused_at": _iso(row.paused_at),
        "created_at": _iso(row.created_at),
        "disconnected_at": _iso(row.disconnected_at),
        "destination_url_saved": bool(row.encrypted_config_blob),
        "destination_url_revealed": False,
        "last_delivery": _serialize_delivery(db, last_delivery) if last_delivery else None,
        "dead_letter_count": dead_letter_count,
        "recoverable_deliveries": [
            _serialize_delivery(db, delivery) for delivery in recoverable_deliveries
        ],
        "automatic_delivery_enabled": (
            row.status == "active" and row.verification_status == "verified"
        ),
        "automatic_actions_enabled": False,
        "conformance_proof": conformance_proof,
    }


def _connection_conformance_proof(
    *,
    row: AutomationWebhookConnection,
    accepted_product_delivery: AutomationWebhookDelivery | None,
) -> dict[str, Any]:
    if row.verification_status == "failed":
        return {
            "state": "needs_attention",
            "label": "Test needs attention",
            "summary": "The saved endpoint has not accepted the current signed test.",
            "evidence_at": _iso(row.last_tested_at),
            "production_proven": False,
        }
    if row.verification_status != "verified":
        return {
            "state": "not_tested",
            "label": "Not tested",
            "summary": "Send a signed test before automatic product events can start.",
            "evidence_at": None,
            "production_proven": False,
        }
    if accepted_product_delivery is not None:
        return {
            "state": "product_event_accepted",
            "label": "Real product event accepted",
            "summary": (
                "The endpoint accepted a signed product event after the current "
                "connection test."
            ),
            "evidence_at": _iso(accepted_product_delivery.delivered_at),
            "production_proven": True,
        }
    return {
        "state": "test_accepted",
        "label": "Signed test accepted",
        "summary": (
            "The endpoint accepted the current signed test. A real product event "
            "has not been proven yet."
        ),
        "evidence_at": _iso(row.last_tested_at),
        "production_proven": False,
    }


def _serialize_delivery(
    db: Session, row: AutomationWebhookDelivery
) -> dict[str, Any]:
    attempts = (
        db.query(AutomationWebhookDeliveryAttempt)
        .filter(AutomationWebhookDeliveryAttempt.delivery_id == row.id)
        .order_by(AutomationWebhookDeliveryAttempt.attempt_number.asc())
        .all()
    )
    job = db.get(PlatformJob, row.platform_job_id) if row.platform_job_id else None
    next_attempt_at = row.next_attempt_at
    if job is not None and job.status == job_service.JOB_STATUS_QUEUED:
        next_attempt_at = job.available_at
    return {
        "id": row.id,
        "connection_id": row.connection_id,
        "event_id": row.event_id,
        "event_type": row.event_type,
        "schema_version": row.schema_version,
        "status": row.status,
        "delivery_kind": row.delivery_kind,
        "attempt_count": row.attempt_count,
        "max_attempts": row.max_attempts,
        "recovery_count": row.recovery_count,
        "last_reason_code": row.last_reason_code,
        "last_response_status": row.last_response_status,
        "last_attempt_at": _iso(row.last_attempt_at),
        "delivered_at": _iso(row.delivered_at),
        "next_attempt_at": _iso(next_attempt_at),
        "dead_lettered_at": _iso(row.dead_lettered_at),
        "cancelled_at": _iso(row.cancelled_at),
        "created_at": _iso(row.created_at),
        "can_retry": (
            row.status == "failed"
            or (row.status == "pending" and row.attempt_count == 0)
        )
        and row.attempt_count < row.max_attempts,
        "can_recover": row.status == "dead_letter",
        "job_status": job.status if job is not None else None,
        "attempts": [
            {
                "attempt_number": item.attempt_number,
                "status": item.status,
                "response_status": item.response_status,
                "reason_code": item.reason_code,
                "duration_ms": item.duration_ms,
                "attempted_at": _iso(item.attempted_at),
            }
            for item in attempts
        ],
    }


def _locked_organization(db: Session, organization_id: str) -> Organization:
    row = (
        db.query(Organization)
        .filter(Organization.id == organization_id)
        .with_for_update()
        .first()
    )
    if row is None:
        raise AutomationWebhookError(
            "Organization not found.",
            reason_code="organization_not_found",
            status_code=404,
        )
    return row


def _locked_connection(
    db: Session, *, organization_id: str, connection_id: str
) -> AutomationWebhookConnection:
    row = (
        db.query(AutomationWebhookConnection)
        .filter(
            AutomationWebhookConnection.id == connection_id,
            AutomationWebhookConnection.organization_id == organization_id,
        )
        .with_for_update()
        .first()
    )
    if row is None:
        raise AutomationWebhookError(
            "Automation connection not found.",
            reason_code="automation_connection_not_found",
            status_code=404,
        )
    return row


def _require_feature(db: Session, organization_id: str) -> None:
    try:
        require_commercial_feature(
            db,
            organization_id=organization_id,
            feature_code=FEATURE_EXTERNAL_AUTOMATION,
        )
    except CostEconomicsError as exc:
        raise AutomationWebhookError(
            str(exc), reason_code=exc.reason_code, status_code=exc.status_code
        ) from exc


def _require_connected_config(row: AutomationWebhookConnection) -> None:
    if row.status == "disconnected" or not row.encrypted_config_blob:
        raise AutomationWebhookError(
            "This automation connection is disconnected.",
            reason_code="automation_connection_disconnected",
        )


def _validate_event_types(values: list[str]) -> list[str]:
    approved = _LIVE_SUBSCRIPTION_TYPES
    normalized = sorted({str(value or "").strip() for value in values if str(value or "").strip()})
    if not normalized or any(value not in approved for value in normalized):
        raise AutomationWebhookError(
            "Choose at least one approved automation event.",
            reason_code="automation_event_subscription_invalid",
            status_code=422,
        )
    return normalized


def _event_types(raw: str) -> list[str]:
    try:
        values = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return [str(value) for value in values] if isinstance(values, list) else []


def _encrypt_config(data: dict[str, Any]) -> tuple[str, str, str]:
    try:
        return encrypt_payload(data)
    except CredentialCryptoError as exc:
        raise AutomationWebhookError(
            "Secure connection storage is not configured.",
            reason_code=exc.reason_code,
        ) from exc


def _decrypt_config(blob: str | None) -> dict[str, Any]:
    if not blob:
        raise AutomationWebhookError(
            "This automation connection has no saved destination.",
            reason_code="automation_connection_disconnected",
        )
    try:
        return decrypt_payload(blob)
    except CredentialCryptoError as exc:
        raise AutomationWebhookError(
            "This automation connection cannot be opened safely.",
            reason_code="automation_connection_secret_unavailable",
        ) from exc


def _destination_error() -> AutomationWebhookError:
    return AutomationWebhookError(
        "Use the complete HTTPS production webhook URL supplied by Zapier, Make, Pipedream, or n8n Cloud.",
        reason_code="automation_destination_invalid",
        status_code=422,
    )


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.isoformat()
