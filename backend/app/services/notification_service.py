from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import json
from typing import Literal

from sqlalchemy import and_, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.automation import AutomationEventEnvelope
from app.events.emitter import EventEnvelope
from app.events.outbox.event_outbox import EventOutbox
from app.models.business_location import BusinessLocation
from app.models.notification import Notification, NotificationUserState
from app.models.organization import Organization
from app.schemas.notification import (
    NotificationItemOut,
    NotificationListOut,
    NotificationMutationOut,
    NotificationUnreadCountOut,
)
from app.services import automation_webhook_service


SCHEMA_VERSION = "alt1-notification-v1"
SEMANTIC_COOLDOWN = timedelta(hours=6)
_MATERIALIZED_INTERNAL_EVENT_TYPES = frozenset(
    {
        "report.generated",
        "report.regenerated",
        "onboarding.baseline_generated",
        "execution.failed",
    }
)
_MATERIALIZED_PRODUCT_EVENT_TYPES = frozenset({"report.ready", "action.failed"})


@dataclass(frozen=True)
class NotificationMaterializationResult:
    notification: Notification | None
    outcome: Literal[
        "created",
        "exact_replay",
        "semantic_cooldown",
        "ignored",
    ]

    @property
    def created(self) -> bool:
        return self.outcome == "created"


class NotificationError(ValueError):
    def __init__(self, message: str, *, reason_code: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.status_code = status_code


def materialize_notification_for_outbox_event(
    db: Session,
    *,
    event: EventEnvelope,
) -> NotificationMaterializationResult:
    """Materialize one supported outbox event into an immutable in-product notice."""
    if event.event_type not in _MATERIALIZED_INTERNAL_EVENT_TYPES:
        return NotificationMaterializationResult(notification=None, outcome="ignored")

    exact = (
        db.query(Notification)
        .filter(
            Notification.tenant_id == event.tenant_id,
            Notification.source_event_id == event.event_id,
        )
        .one_or_none()
    )
    if exact is not None:
        return NotificationMaterializationResult(
            notification=exact,
            outcome="exact_replay",
        )

    source = (
        db.query(EventOutbox)
        .filter(
            EventOutbox.id == event.event_id,
            EventOutbox.tenant_id == event.tenant_id,
        )
        .one_or_none()
    )
    if source is None:
        return NotificationMaterializationResult(notification=None, outcome="ignored")
    normalized = automation_webhook_service._translate_product_event(
        db,
        source=source,
        event=event,
    )
    if normalized is None or normalized.event_type not in _MATERIALIZED_PRODUCT_EVENT_TYPES:
        return NotificationMaterializationResult(notification=None, outcome="ignored")

    organization = db.get(Organization, normalized.organization_id)
    if organization is None:
        return NotificationMaterializationResult(notification=None, outcome="ignored")
    location = _notification_location(db, event=normalized)
    values = _notification_values(
        event=normalized,
        source_event_type=event.event_type,
        organization=organization,
        location=location,
    )
    semantic_fingerprint = str(values["semantic_fingerprint"])
    observed_at = values["observed_at"]
    if not isinstance(observed_at, datetime):
        raise TypeError("notification observed_at must be a datetime")
    _lock_semantic_fingerprint(
        db,
        organization_id=normalized.organization_id,
        semantic_fingerprint=semantic_fingerprint,
    )
    existing = _semantic_repeat(
        db,
        tenant_id=event.tenant_id,
        semantic_fingerprint=semantic_fingerprint,
        observed_at=observed_at,
    )
    if existing is not None:
        return NotificationMaterializationResult(
            notification=existing,
            outcome="semantic_cooldown",
        )

    row = Notification(
        tenant_id=event.tenant_id,
        organization_id=normalized.organization_id,
        source_event_id=event.event_id,
        **values,
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        exact = (
            db.query(Notification)
            .filter(
                Notification.tenant_id == event.tenant_id,
                Notification.source_event_id == event.event_id,
            )
            .one_or_none()
        )
        if exact is not None:
            return NotificationMaterializationResult(
                notification=exact,
                outcome="exact_replay",
            )
        existing = _semantic_repeat(
            db,
            tenant_id=event.tenant_id,
            semantic_fingerprint=semantic_fingerprint,
            observed_at=observed_at,
        )
        if existing is not None:
            return NotificationMaterializationResult(
                notification=existing,
                outcome="semantic_cooldown",
            )
        raise
    return NotificationMaterializationResult(notification=row, outcome="created")


def list_notifications(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    user_id: str,
    location_id: str | None = None,
    include_dismissed: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> NotificationListOut:
    state_join = and_(
        NotificationUserState.notification_id == Notification.id,
        NotificationUserState.tenant_id == Notification.tenant_id,
        NotificationUserState.organization_id == Notification.organization_id,
        NotificationUserState.user_id == user_id,
    )
    query = (
        db.query(Notification, NotificationUserState)
        .outerjoin(NotificationUserState, state_join)
        .filter(
            Notification.tenant_id == tenant_id,
            Notification.organization_id == organization_id,
        )
    )
    if location_id is not None:
        query = query.filter(Notification.location_id == location_id)
    if not include_dismissed:
        query = query.filter(NotificationUserState.dismissed_at.is_(None))
    total = query.count()
    rows = (
        query.order_by(Notification.observed_at.desc(), Notification.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return NotificationListOut(
        items=[serialize_notification(notification, state=state) for notification, state in rows],
        unread_count=unread_notification_count(
            db,
            tenant_id=tenant_id,
            organization_id=organization_id,
            user_id=user_id,
            location_id=location_id,
        ),
        total=total,
        limit=limit,
        offset=offset,
    )


def unread_notification_count(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    user_id: str,
    location_id: str | None = None,
) -> int:
    state_join = and_(
        NotificationUserState.notification_id == Notification.id,
        NotificationUserState.tenant_id == Notification.tenant_id,
        NotificationUserState.organization_id == Notification.organization_id,
        NotificationUserState.user_id == user_id,
    )
    query = (
        db.query(Notification.id)
        .outerjoin(NotificationUserState, state_join)
        .filter(
            Notification.tenant_id == tenant_id,
            Notification.organization_id == organization_id,
            NotificationUserState.read_at.is_(None),
            NotificationUserState.dismissed_at.is_(None),
        )
    )
    if location_id is not None:
        query = query.filter(Notification.location_id == location_id)
    return query.count()


def notification_unread_count_payload(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    user_id: str,
    location_id: str | None = None,
) -> NotificationUnreadCountOut:
    count = unread_notification_count(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        user_id=user_id,
        location_id=location_id,
    )
    return NotificationUnreadCountOut(unread_count=count, count=count)


def mark_notification_read(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    user_id: str,
    notification_id: str,
    now: datetime | None = None,
) -> NotificationMutationOut:
    notification = _scoped_notification(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        notification_id=notification_id,
    )
    changed_at = _as_utc(now or datetime.now(UTC))
    state = _mutate_user_state(
        db,
        notification=notification,
        user_id=user_id,
        read_at=changed_at,
        dismiss=False,
    )
    db.flush()
    return NotificationMutationOut(
        notification=serialize_notification(notification, state=state),
        unread_count=unread_notification_count(
            db,
            tenant_id=tenant_id,
            organization_id=organization_id,
            user_id=user_id,
        ),
    )


def dismiss_notification(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    user_id: str,
    notification_id: str,
    now: datetime | None = None,
) -> NotificationMutationOut:
    notification = _scoped_notification(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        notification_id=notification_id,
    )
    changed_at = _as_utc(now or datetime.now(UTC))
    state = _mutate_user_state(
        db,
        notification=notification,
        user_id=user_id,
        read_at=changed_at,
        dismiss=True,
    )
    db.flush()
    return NotificationMutationOut(
        notification=serialize_notification(notification, state=state),
        unread_count=unread_notification_count(
            db,
            tenant_id=tenant_id,
            organization_id=organization_id,
            user_id=user_id,
        ),
    )


def serialize_notification(
    notification: Notification,
    *,
    state: NotificationUserState | None,
) -> NotificationItemOut:
    return NotificationItemOut(
        id=notification.id,
        schema_version=notification.schema_version,
        organization_id=notification.organization_id,
        organization_name=notification.organization_name,
        location_id=notification.location_id,
        location_name=notification.location_name,
        event_type=notification.event_type,
        severity=notification.severity,
        source_event_id=notification.source_event_id,
        source_event_type=notification.source_event_type,
        source_label=notification.source_label,
        resource_type=notification.resource_type,
        resource_id=notification.resource_id,
        title=notification.title,
        meaning=notification.meaning,
        action_label=notification.action_label,
        action_url=notification.action_url,
        freshness_at=_as_utc(notification.freshness_at),
        observed_at=_as_utc(notification.observed_at),
        created_at=_as_utc(notification.created_at),
        is_read=state is not None and state.read_at is not None,
        read_at=_as_utc(state.read_at) if state is not None and state.read_at else None,
        is_dismissed=state is not None and state.dismissed_at is not None,
        dismissed_at=(
            _as_utc(state.dismissed_at)
            if state is not None and state.dismissed_at
            else None
        ),
    )


def _notification_location(
    db: Session,
    *,
    event: AutomationEventEnvelope,
) -> BusinessLocation | None:
    if event.location_id is None:
        return None
    return (
        db.query(BusinessLocation)
        .filter(
            BusinessLocation.id == event.location_id,
            BusinessLocation.organization_id == event.organization_id,
        )
        .one_or_none()
    )


def _notification_values(
    *,
    event: AutomationEventEnvelope,
    source_event_type: str,
    organization: Organization,
    location: BusinessLocation | None,
) -> dict[str, object]:
    observed_at = _as_utc(event.occurred_at)
    if event.event_type == "report.ready":
        report_label = _normalized_copy(
            str(event.data.get("report_label") or "Saved report"),
            max_length=150,
        )
        source_label = "Saved reports"
        severity = "information"
        title = f"{report_label} is ready"
        meaning = str(
            event.data.get("summary")
            or "A saved report is ready for review."
        )
        action_label = "Review report"
        freshness_at = _contract_datetime(
            event.data.get("observed_through"),
            fallback=observed_at,
        )
    else:
        source_label = "Approved actions"
        severity = "needs_attention"
        title = _normalized_copy(
            str(event.data.get("title") or "Approved action needs attention"),
            max_length=180,
        )
        meaning = str(
            event.data.get("summary")
            or "An approved action stopped and needs review."
        )
        action_label = "Review recovery guidance"
        freshness_at = _contract_datetime(
            event.data.get("failed_at"),
            fallback=observed_at,
        )
    semantic_fingerprint = _semantic_fingerprint(
        organization_id=event.organization_id,
        location_id=event.location_id,
        event_type=event.event_type,
        resource_type=event.resource.type,
        resource_id=event.resource.id,
        action_url=event.resource.href,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "location_id": event.location_id,
        "organization_name": organization.name,
        "location_name": location.name if location is not None else None,
        "event_type": event.event_type,
        "severity": severity,
        "source_event_type": source_event_type,
        "source_label": source_label,
        "resource_type": event.resource.type,
        "resource_id": event.resource.id,
        "title": title,
        "meaning": _normalized_copy(meaning, max_length=2_000),
        "action_label": action_label,
        "action_url": event.resource.href,
        "freshness_at": freshness_at,
        "observed_at": observed_at,
        "semantic_fingerprint": semantic_fingerprint,
        "cooldown_window_started_at": observed_at,
        "cooldown_expires_at": observed_at + SEMANTIC_COOLDOWN,
        "created_at": datetime.now(UTC),
    }


def _semantic_fingerprint(
    *,
    organization_id: str,
    location_id: str | None,
    event_type: str,
    resource_type: str,
    resource_id: str,
    action_url: str,
) -> str:
    canonical = json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "organization_id": organization_id,
            "location_id": location_id,
            "event_type": event_type,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "action_url": action_url,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _lock_semantic_fingerprint(
    db: Session,
    *,
    organization_id: str,
    semantic_fingerprint: str,
) -> None:
    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        return
    digest = hashlib.sha256(
        f"{organization_id}:{semantic_fingerprint}".encode("utf-8")
    ).digest()
    lock_key = int.from_bytes(digest[:8], byteorder="big", signed=True)
    db.execute(
        text("SELECT pg_advisory_xact_lock(:lock_key)"),
        {"lock_key": lock_key},
    )


def _semantic_repeat(
    db: Session,
    *,
    tenant_id: str,
    semantic_fingerprint: str,
    observed_at: datetime,
) -> Notification | None:
    return (
        db.query(Notification)
        .filter(
            Notification.tenant_id == tenant_id,
            Notification.semantic_fingerprint == semantic_fingerprint,
            Notification.observed_at > observed_at - SEMANTIC_COOLDOWN,
            Notification.observed_at < observed_at + SEMANTIC_COOLDOWN,
        )
        .order_by(Notification.observed_at.desc(), Notification.id.desc())
        .first()
    )


def _contract_datetime(value: object, *, fallback: datetime) -> datetime:
    if isinstance(value, datetime):
        return _as_utc(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return fallback
        return _as_utc(parsed)
    return fallback


def _normalized_copy(value: str, *, max_length: int) -> str:
    return " ".join(value.strip().split())[:max_length]


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _scoped_notification(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    notification_id: str,
) -> Notification:
    row = (
        db.query(Notification)
        .filter(
            Notification.id == notification_id,
            Notification.tenant_id == tenant_id,
            Notification.organization_id == organization_id,
        )
        .one_or_none()
    )
    if row is None:
        raise NotificationError(
            "Notification not found.",
            reason_code="notification_not_found",
            status_code=404,
        )
    return row


def _mutate_user_state(
    db: Session,
    *,
    notification: Notification,
    user_id: str,
    read_at: datetime,
    dismiss: bool,
) -> NotificationUserState:
    state = (
        db.query(NotificationUserState)
        .filter(
            NotificationUserState.notification_id == notification.id,
            NotificationUserState.tenant_id == notification.tenant_id,
            NotificationUserState.organization_id == notification.organization_id,
            NotificationUserState.user_id == user_id,
        )
        .one_or_none()
    )
    if state is None:
        state = NotificationUserState(
            tenant_id=notification.tenant_id,
            organization_id=notification.organization_id,
            notification_id=notification.id,
            user_id=user_id,
            read_at=read_at,
            dismissed_at=read_at if dismiss else None,
            created_at=read_at,
            updated_at=read_at,
        )
        try:
            with db.begin_nested():
                db.add(state)
                db.flush()
        except IntegrityError:
            state = (
                db.query(NotificationUserState)
                .filter(
                    NotificationUserState.notification_id == notification.id,
                    NotificationUserState.user_id == user_id,
                )
                .one()
            )
    changed = False
    if state.read_at is None:
        state.read_at = read_at
        changed = True
    if dismiss and state.dismissed_at is None:
        state.dismissed_at = read_at
        changed = True
    if changed:
        state.updated_at = read_at
    return state
