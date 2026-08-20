from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.launch_experience import LaunchExperienceReview


SCHEMA_VERSION = "ops1-launch-experience-v1"
REVIEW_SCHEMA_VERSION = "ops1-experience-review-v1"
REVIEW_MAX_AGE = timedelta(days=7)
REVIEW_MAX_VALIDITY = timedelta(days=45)
MODERATED_SUBJECT = "first_use_complete_journey"

ROUTE_CATALOG = (
    ("overview", "Overview", "/dashboard"),
    ("next_steps", "Next Steps", "/opportunities"),
    ("customer_reviews", "Customer Reviews", "/reviews"),
    ("reports", "Reports", "/reports"),
    ("search_rankings", "Search Rankings", "/rankings"),
    ("local_search", "Local Search", "/local-visibility"),
    ("website_health", "Website Health", "/site-health"),
    ("search_value", "Search Value", "/organic-value"),
    ("ai_search", "AI Search", "/ai-visibility"),
    ("find_searches", "Find Searches", "/keyword-research"),
    ("competitors", "Competitors", "/competitors"),
    ("content", "Content", "/content"),
    ("directory_listings", "Directory Listings", "/citations"),
    ("profile_campaigns", "Profile Campaigns", "/profile-campaigns"),
    ("locations", "Locations", "/locations"),
    ("settings_connections", "Settings & Connections", "/settings"),
    ("client_access", "Client Access", "/client-access"),
    ("team_activity", "Team Activity", "/activity"),
    ("help_center", "Help Center", "/help"),
)
ROUTES_BY_CODE = {code: {"code": code, "label": label, "path": path} for code, label, path in ROUTE_CATALOG}

SENSITIVE_PATTERN = re.compile(
    r"(?i)(https?://|\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b|bearer\s+|whsec_|"
    r"sk_(?:live|test)_|xox[baprs]-|\b(?:google|stripe|zapier|make\.com|n8n|"
    r"dataforseo|mistral|openai|supabase|vercel)\b|[A-Za-z0-9_-]{48,})"
)
SESSION_REFERENCE_PATTERN = re.compile(r"^[A-Z][A-Z0-9-]{5,39}$")


class LaunchExperienceError(ValueError):
    def __init__(self, message: str, *, reason_code: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.status_code = status_code


def create_launch_experience_review(
    db: Session,
    *,
    review_kind: str,
    subject_code: str,
    viewport: str,
    result: str,
    session_reference: str | None,
    summary: str,
    issue_count: int,
    blocking_issue_count: int,
    evidence_reference: str,
    observed_at: datetime,
    expires_at: datetime,
    recorded_by_user_id: str,
    now: datetime | None = None,
) -> tuple[LaunchExperienceReview, bool]:
    evaluated = _as_utc(now or datetime.now(UTC))
    clean_summary = " ".join(summary.split())
    clean_evidence = " ".join(evidence_reference.split())
    clean_session = " ".join((session_reference or "").split()).upper() or None

    if review_kind not in {"route_audit", "moderated_session"}:
        raise LaunchExperienceError(
            "Choose route audit or moderated session.",
            reason_code="launch_experience_kind_invalid",
        )
    if result not in {"passed", "failed"}:
        raise LaunchExperienceError(
            "Choose whether the review passed or failed.",
            reason_code="launch_experience_result_invalid",
        )
    if issue_count < 0 or blocking_issue_count < 0 or blocking_issue_count > issue_count:
        raise LaunchExperienceError(
            "Issue counts must be zero or greater, and blockers cannot exceed all issues.",
            reason_code="launch_experience_issue_counts_invalid",
        )
    if result == "passed" and blocking_issue_count:
        raise LaunchExperienceError(
            "A passing review cannot retain a blocking issue.",
            reason_code="launch_experience_blocker_conflict",
        )
    if review_kind == "route_audit":
        if subject_code not in ROUTES_BY_CODE:
            raise LaunchExperienceError(
                "Choose a route from the current customer navigation.",
                reason_code="launch_experience_route_invalid",
            )
        if viewport not in {"desktop", "mobile"}:
            raise LaunchExperienceError(
                "Route audits require desktop or mobile.",
                reason_code="launch_experience_viewport_invalid",
            )
        if clean_session is not None:
            raise LaunchExperienceError(
                "Route audits do not use a participant reference.",
                reason_code="launch_experience_session_conflict",
            )
    else:
        if subject_code != MODERATED_SUBJECT or viewport != "not_applicable":
            raise LaunchExperienceError(
                "Moderated sessions use the complete first-use journey without a viewport.",
                reason_code="launch_experience_moderated_scope_invalid",
            )
        if clean_session is None or not SESSION_REFERENCE_PATTERN.fullmatch(clean_session):
            raise LaunchExperienceError(
                "Use an opaque participant alias such as UX-0001; never use a name or email.",
                reason_code="launch_experience_session_reference_invalid",
            )

    if not 20 <= len(clean_summary) <= 400:
        raise LaunchExperienceError(
            "Summarize the observed result in 20 to 400 characters.",
            reason_code="launch_experience_summary_invalid",
        )
    if not 8 <= len(clean_evidence) <= 160:
        raise LaunchExperienceError(
            "Use a short internal evidence reference between 8 and 160 characters.",
            reason_code="launch_experience_reference_invalid",
        )
    if any(SENSITIVE_PATTERN.search(value) for value in (clean_summary, clean_evidence, clean_session or "")):
        raise LaunchExperienceError(
            "Use opaque internal references and plain findings without links, people, suppliers, or secrets.",
            reason_code="launch_experience_sensitive_value_rejected",
        )

    observed = _as_utc(observed_at)
    expires = _as_utc(expires_at)
    if observed > evaluated + timedelta(minutes=5) or observed < evaluated - REVIEW_MAX_AGE:
        raise LaunchExperienceError(
            "The review must have been observed within the last seven days.",
            reason_code="launch_experience_observed_at_invalid",
        )
    if expires <= evaluated or expires <= observed or expires > observed + REVIEW_MAX_VALIDITY:
        raise LaunchExperienceError(
            "The recheck date must be after today and within 45 days of observation.",
            reason_code="launch_experience_expiry_invalid",
        )

    digest_payload = {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "review_kind": review_kind,
        "subject_code": subject_code,
        "viewport": viewport,
        "result": result,
        "session_reference": clean_session,
        "summary": clean_summary,
        "issue_count": issue_count,
        "blocking_issue_count": blocking_issue_count,
        "evidence_reference": clean_evidence,
        "observed_at": observed.isoformat(),
        "expires_at": expires.isoformat(),
    }
    evidence_digest = _digest(digest_payload)
    existing = db.query(LaunchExperienceReview).filter(
        LaunchExperienceReview.evidence_digest == evidence_digest
    ).one_or_none()
    if existing is not None:
        return existing, False

    row = LaunchExperienceReview(
        schema_version=REVIEW_SCHEMA_VERSION,
        review_kind=review_kind,
        subject_code=subject_code,
        viewport=viewport,
        result=result,
        session_reference=clean_session,
        summary=clean_summary,
        issue_count=issue_count,
        blocking_issue_count=blocking_issue_count,
        evidence_reference=clean_evidence,
        evidence_digest=evidence_digest,
        recorded_by_user_id=recorded_by_user_id,
        observed_at=observed,
        expires_at=expires,
        created_at=evaluated,
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        exact = db.query(LaunchExperienceReview).filter(
            LaunchExperienceReview.evidence_digest == evidence_digest
        ).one_or_none()
        if exact is not None:
            return exact, False
        raise
    return row, True


def serialize_launch_experience_review(
    row: LaunchExperienceReview, *, now: datetime
) -> dict[str, Any]:
    expires = _as_utc(row.expires_at)
    return {
        "id": row.id,
        "review_kind": row.review_kind,
        "subject_code": row.subject_code,
        "viewport": row.viewport,
        "result": row.result,
        "session_reference": row.session_reference,
        "summary": row.summary,
        "issue_count": row.issue_count,
        "blocking_issue_count": row.blocking_issue_count,
        "evidence_reference": row.evidence_reference,
        "observed_at": _as_utc(row.observed_at).isoformat(),
        "expires_at": expires.isoformat(),
        "current": expires > now,
    }


def build_launch_experience_readiness(
    db: Session, *, evaluated_at: datetime | None = None
) -> dict[str, Any]:
    now = _as_utc(evaluated_at or datetime.now(UTC))
    rows = db.query(LaunchExperienceReview).order_by(
        LaunchExperienceReview.observed_at.desc(),
        LaunchExperienceReview.created_at.desc(),
        LaunchExperienceReview.id.desc(),
    ).all()
    latest_route: dict[tuple[str, str], LaunchExperienceReview] = {}
    latest_session: dict[str, LaunchExperienceReview] = {}
    for row in rows:
        if row.review_kind == "route_audit":
            latest_route.setdefault((row.subject_code, row.viewport), row)
        elif row.session_reference:
            latest_session.setdefault(row.session_reference, row)

    route_items: list[dict[str, Any]] = []
    route_basis: list[dict[str, Any]] = []
    newest_route: datetime | None = None
    for code, label, path in ROUTE_CATALOG:
        viewport_states: dict[str, Any] = {}
        for viewport in ("desktop", "mobile"):
            review = latest_route.get((code, viewport))
            if review is None:
                state = "missing"
                payload = None
            else:
                newest_route = _max_datetime(newest_route, _as_utc(review.observed_at))
                payload = serialize_launch_experience_review(review, now=now)
                state = review.result if payload["current"] else "stale"
            viewport_states[viewport] = {"state": state, "review": payload}
            route_basis.append(
                {
                    "code": code,
                    "viewport": viewport,
                    "state": state,
                    "review_id": review.id if review else None,
                    "expires_at": _as_utc(review.expires_at).isoformat() if review else None,
                }
            )
        route_items.append(
            {
                "code": code,
                "label": label,
                "path": path,
                "state": (
                    "failed"
                    if any(item["state"] == "failed" for item in viewport_states.values())
                    else "stale"
                    if any(item["state"] == "stale" for item in viewport_states.values())
                    else "missing"
                    if any(item["state"] == "missing" for item in viewport_states.values())
                    else "passed"
                ),
                "viewports": viewport_states,
            }
        )

    session_items: list[dict[str, Any]] = []
    newest_session: datetime | None = None
    for session_reference, review in sorted(latest_session.items()):
        newest_session = _max_datetime(newest_session, _as_utc(review.observed_at))
        payload = serialize_launch_experience_review(review, now=now)
        state = review.result if payload["current"] else "stale"
        session_items.append({"session_reference": session_reference, "state": state, "review": payload})

    route_counts = {
        state: sum(1 for item in route_items if item["state"] == state)
        for state in ("passed", "failed", "stale", "missing")
    }
    session_counts = {
        state: sum(1 for item in session_items if item["state"] == state)
        for state in ("passed", "failed", "stale")
    }
    session_counts["required"] = 5
    session_counts["remaining"] = max(0, 5 - session_counts["passed"])
    route_state = (
        "blocked" if route_counts["failed"] else "ready" if route_counts["passed"] == len(ROUTE_CATALOG) else "incomplete"
    )
    moderated_state = (
        "blocked" if session_counts["failed"] else "ready" if session_counts["passed"] >= 5 else "incomplete"
    )
    basis_digest = _digest(
        {
            "schema_version": SCHEMA_VERSION,
            "routes": route_basis,
            "sessions": [
                {
                    "session_reference": item["session_reference"],
                    "state": item["state"],
                    "review_id": item["review"]["id"],
                    "expires_at": item["review"]["expires_at"],
                }
                for item in session_items
            ],
        }
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "evaluated_at": now.isoformat(),
        "basis_digest": basis_digest,
        "evidence_state": (
            "blocked" if "blocked" in {route_state, moderated_state} else "ready" if route_state == moderated_state == "ready" else "incomplete"
        ),
        "route_audit": {
            "evidence_state": route_state,
            "required_route_count": len(ROUTE_CATALOG),
            "required_viewport_count": len(ROUTE_CATALOG) * 2,
            "latest_observed_at": newest_route.isoformat() if newest_route else None,
            "counts": route_counts,
            "routes": route_items,
        },
        "moderated_sessions": {
            "evidence_state": moderated_state,
            "latest_observed_at": newest_session.isoformat() if newest_session else None,
            "counts": session_counts,
            "sessions": session_items,
        },
        "limitations": [
            "Automated tests do not count as a route audit or moderated session.",
            "Participant references are opaque aliases; names, email addresses, recordings, and links are not stored here.",
            "A passing structured review still requires a platform-owner launch proof of the exact evidence set.",
        ],
    }


def _digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _max_datetime(left: datetime | None, right: datetime) -> datetime:
    return max(left, right) if left else right


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
