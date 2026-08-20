from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.customer_status import CustomerStatusUpdate


SCHEMA_VERSION = "ops1-customer-status-v1"
STATES = {"investigating", "identified", "monitoring", "resolved", "maintenance"}
IMPACTS = {"none", "minor", "major", "critical"}
SURFACE_LABELS = {
    "dashboard": "Overview",
    "website_analysis": "Website analysis",
    "rankings": "Rank tracking",
    "local_visibility": "Local visibility",
    "reviews": "Reviews",
    "reports": "Reports",
    "automations": "Automations",
    "billing": "Billing",
    "connections": "Connections",
    "sign_in": "Sign in",
}
INCIDENT_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")
SENSITIVE_COPY_PATTERN = re.compile(
    r"(?i)(https?://|bearer\s+|traceback|stack trace|sqlalchemy|postgres|stripe|openai|"
    r"data[\s_-]*for[\s_-]*seo|google|microsoft|zapier|make\.com|n8n|"
    r"\b(?:provider|supplier|vendor)\b|whsec_|sk_(?:live|test)_|"
    r"xox[baprs]-|[A-Za-z0-9_-]{48,})"
)


class CustomerStatusError(ValueError):
    def __init__(self, message: str, *, reason_code: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.status_code = status_code


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _normalized_copy(value: str) -> str:
    return " ".join(value.strip().split())


def _validate_safe_copy(*values: str) -> None:
    if any(SENSITIVE_COPY_PATTERN.search(value) for value in values):
        raise CustomerStatusError(
            "Use customer-facing language without links, supplier names, credentials, or internal errors.",
            reason_code="customer_status_sensitive_copy_rejected",
        )


def _digest(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def create_customer_status_update(
    db: Session,
    *,
    incident_key: str,
    state: str,
    impact: str,
    title: str,
    message: str,
    affected_surfaces: list[str],
    visible_to_customers: bool,
    starts_at: datetime,
    ends_at: datetime | None,
    created_by_user_id: str,
) -> tuple[CustomerStatusUpdate, bool]:
    incident_key = incident_key.strip().lower()
    state = state.strip().lower()
    impact = impact.strip().lower()
    title = _normalized_copy(title)
    message = _normalized_copy(message)
    surfaces = sorted(set(affected_surfaces))
    starts_at = _as_utc(starts_at)
    ends_at = _as_utc(ends_at) if ends_at else None

    if not INCIDENT_KEY_PATTERN.fullmatch(incident_key):
        raise CustomerStatusError(
            "Incident key must use lowercase letters, numbers, and hyphens.",
            reason_code="customer_status_incident_key_invalid",
        )
    if state not in STATES or impact not in IMPACTS:
        raise CustomerStatusError(
            "Choose a supported incident state and impact.",
            reason_code="customer_status_state_invalid",
        )
    unknown_surfaces = sorted(set(surfaces) - set(SURFACE_LABELS))
    if not surfaces or unknown_surfaces:
        raise CustomerStatusError(
            "Choose at least one supported customer area.",
            reason_code="customer_status_surface_invalid",
        )
    if not (8 <= len(title) <= 100) or not (20 <= len(message) <= 500):
        raise CustomerStatusError(
            "Add a short title and a clear customer update.",
            reason_code="customer_status_copy_invalid",
        )
    _validate_safe_copy(title, message)
    if starts_at > datetime.now(UTC) + timedelta(days=90):
        raise CustomerStatusError(
            "The status window cannot begin more than 90 days from now.",
            reason_code="customer_status_window_invalid",
        )
    if ends_at is not None and ends_at <= starts_at:
        raise CustomerStatusError(
            "The end time must be after the start time.",
            reason_code="customer_status_window_invalid",
        )
    if state == "maintenance" and ends_at is None:
        raise CustomerStatusError(
            "A maintenance notice needs an expected end time.",
            reason_code="customer_status_window_invalid",
        )
    if state == "resolved" and ends_at is None:
        raise CustomerStatusError(
            "A resolved update needs a resolution time.",
            reason_code="customer_status_window_invalid",
        )

    digest_payload = {
        "schema_version": SCHEMA_VERSION,
        "incident_key": incident_key,
        "state": state,
        "impact": impact,
        "title": title,
        "message": message,
        "affected_surfaces": surfaces,
        "visible_to_customers": visible_to_customers,
        "starts_at": starts_at.isoformat(),
        "ends_at": ends_at.isoformat() if ends_at else None,
    }
    content_digest = _digest(digest_payload)
    existing = (
        db.query(CustomerStatusUpdate)
        .filter(CustomerStatusUpdate.content_digest == content_digest)
        .first()
    )
    if existing is not None:
        return existing, False

    latest = (
        db.query(CustomerStatusUpdate)
        .filter(CustomerStatusUpdate.incident_key == incident_key)
        .order_by(CustomerStatusUpdate.update_number.desc())
        .with_for_update()
        .first()
    )
    row = CustomerStatusUpdate(
        schema_version=SCHEMA_VERSION,
        incident_key=incident_key,
        update_number=(latest.update_number + 1) if latest else 1,
        state=state,
        impact=impact,
        title=title,
        message=message,
        affected_surfaces=surfaces,
        visible_to_customers=visible_to_customers,
        starts_at=starts_at,
        ends_at=ends_at,
        content_digest=content_digest,
        created_by_user_id=created_by_user_id,
        created_at=datetime.now(UTC),
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError as exc:
        exact = (
            db.query(CustomerStatusUpdate)
            .filter(CustomerStatusUpdate.content_digest == content_digest)
            .first()
        )
        if exact is not None:
            return exact, False
        raise CustomerStatusError(
            "A newer update was saved at the same time. Reload and try again.",
            reason_code="customer_status_update_conflict",
            status_code=409,
        ) from exc
    return row, True


def serialize_customer_status_update(row: CustomerStatusUpdate, *, internal: bool) -> dict:
    payload = {
        "id": row.id,
        "incident_key": row.incident_key,
        "update_number": row.update_number,
        "state": row.state,
        "impact": row.impact,
        "title": row.title,
        "message": row.message,
        "affected_surfaces": [
            {"code": code, "label": SURFACE_LABELS[code]}
            for code in row.affected_surfaces
            if code in SURFACE_LABELS
        ],
        "starts_at": _as_utc(row.starts_at).isoformat(),
        "ends_at": _as_utc(row.ends_at).isoformat() if row.ends_at else None,
        "updated_at": _as_utc(row.created_at).isoformat(),
    }
    if internal:
        payload["visible_to_customers"] = row.visible_to_customers
    return payload


def customer_status_summary(db: Session, *, now: datetime | None = None) -> dict:
    current_time = _as_utc(now or datetime.now(UTC))
    rows = (
        db.query(CustomerStatusUpdate)
        .filter(CustomerStatusUpdate.visible_to_customers.is_(True))
        .order_by(CustomerStatusUpdate.created_at.desc(), CustomerStatusUpdate.update_number.desc())
        .all()
    )
    latest_by_incident: dict[str, CustomerStatusUpdate] = {}
    for row in rows:
        latest_by_incident.setdefault(row.incident_key, row)

    active: list[CustomerStatusUpdate] = []
    for row in latest_by_incident.values():
        if row.state == "resolved":
            continue
        if row.ends_at is not None and _as_utc(row.ends_at) <= current_time:
            continue
        active.append(row)
    severity = {"critical": 0, "major": 1, "minor": 2, "none": 3}
    active.sort(key=lambda item: (severity.get(item.impact, 4), _as_utc(item.starts_at)))
    return {
        "schema_version": SCHEMA_VERSION,
        "state": (
            "degraded"
            if any(
                row.impact in {"major", "critical"}
                and _as_utc(row.starts_at) <= current_time
                for row in active
            )
            else ("notice" if active else "operational")
        ),
        "incidents": [serialize_customer_status_update(row, internal=False) for row in active],
        "checked_at": current_time.isoformat(),
    }


def customer_status_history(db: Session, *, limit: int = 100) -> dict:
    rows = (
        db.query(CustomerStatusUpdate)
        .order_by(CustomerStatusUpdate.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "updates": [serialize_customer_status_update(row, internal=True) for row in rows],
        "active": customer_status_summary(db),
    }
