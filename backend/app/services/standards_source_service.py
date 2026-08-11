from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from difflib import SequenceMatcher
from hashlib import sha256
from html.parser import HTMLParser
import json
import re
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from app.models.reference_library import (
    StandardsChangeCandidate,
    StandardsImpactLink,
    StandardsSourceRegistry,
    StandardsSourceSnapshot,
)


PARSER_VERSION = "i1.6a.v1"
CLASSIFICATION_VERSION = "i1.6b.v1"
DEFAULT_MAX_CONTENT_BYTES = 1_000_000
ALLOWED_SOURCE_HOSTS = frozenset(
    {
        "developers.google.com",
        "status.search.google.com",
        "support.google.com",
    }
)
BLOCKING_CANDIDATE_STATUSES = frozenset({"needs_review", "requires_contract_update"})
REVIEW_DISPOSITIONS = frozenset(
    {"requires_contract_update", "no_product_impact", "editorial_only", "reopen"}
)


class StandardsContractBlockedError(RuntimeError):
    def __init__(self, adapter_key: str, candidate_id: str) -> None:
        super().__init__(
            "This provider is paused while an official measurement or API change is reviewed."
        )
        self.adapter_key = adapter_key
        self.candidate_id = candidate_id


@dataclass(frozen=True)
class ClassifiedStandardsChange:
    change_type: str
    materiality: str
    status: str
    title: str
    summary: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class StandardsSourceDefinition:
    source_id: str
    display_name: str
    source_uri: str
    source_format: str
    source_scope: str
    review_interval_hours: int
    source_owner: str = "Google"
    parser_version: str = PARSER_VERSION


DEFAULT_STANDARDS_SOURCES: tuple[StandardsSourceDefinition, ...] = (
    StandardsSourceDefinition(
        source_id="google.search.docs_updates",
        display_name="Google Search documentation updates",
        source_uri="https://developers.google.com/search/updates/search_docs_updates.rss",
        source_format="rss",
        source_scope="search_guidance",
        review_interval_hours=24,
    ),
    StandardsSourceDefinition(
        source_id="google.search.status_incidents",
        display_name="Google Search status incidents",
        source_uri="https://status.search.google.com/incidents.json",
        source_format="json",
        source_scope="search_status",
        review_interval_hours=6,
    ),
    StandardsSourceDefinition(
        source_id="google.search.ranking_systems",
        display_name="Google Search ranking systems guide",
        source_uri="https://developers.google.com/search/docs/appearance/ranking-systems-guide",
        source_format="html",
        source_scope="search_guidance",
        review_interval_hours=168,
    ),
    StandardsSourceDefinition(
        source_id="google.search.core_web_vitals",
        display_name="Google Search Core Web Vitals guidance",
        source_uri="https://developers.google.com/search/docs/appearance/core-web-vitals",
        source_format="html",
        source_scope="website_measurements",
        review_interval_hours=168,
    ),
    StandardsSourceDefinition(
        source_id="google.search.structured_data",
        display_name="Google Search structured data guidance",
        source_uri=(
            "https://developers.google.com/search/docs/appearance/structured-data/"
            "intro-structured-data"
        ),
        source_format="html",
        source_scope="website_measurements",
        review_interval_hours=168,
    ),
    StandardsSourceDefinition(
        source_id="google.search_console.metrics",
        display_name="Google Search Console metric definitions",
        source_uri="https://support.google.com/webmasters/answer/7042828?hl=en",
        source_format="html",
        source_scope="search_console_metrics",
        review_interval_hours=168,
    ),
    StandardsSourceDefinition(
        source_id="google.business.local_ranking",
        display_name="Google local ranking guidance",
        source_uri="https://support.google.com/business/answer/7091?hl=en",
        source_format="html",
        source_scope="business_profile_guidance",
        review_interval_hours=168,
    ),
    StandardsSourceDefinition(
        source_id="google.business.api_change_log",
        display_name="Google Business Profile API change log",
        source_uri="https://developers.google.com/my-business/content/change-log",
        source_format="html",
        source_scope="business_profile_api",
        review_interval_hours=24,
    ),
    StandardsSourceDefinition(
        source_id="google.business.information_change_log",
        display_name="Google Business Information API change log",
        source_uri=(
            "https://developers.google.com/my-business/content/businessinformation/"
            "change-log"
        ),
        source_format="html",
        source_scope="business_profile_api",
        review_interval_hours=24,
    ),
    StandardsSourceDefinition(
        source_id="google.business.performance_reference",
        display_name="Google Business Profile Performance API reference",
        source_uri=(
            "https://developers.google.com/my-business/reference/performance/rpc/"
            "google.mybusiness.performance.v1"
        ),
        source_format="html",
        source_scope="business_profile_metrics",
        review_interval_hours=168,
    ),
)


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"} and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth and data.strip():
            self.parts.append(data)


def ensure_default_sources(
    db: Session,
    *,
    now: datetime | None = None,
    commit: bool = True,
) -> list[StandardsSourceRegistry]:
    observed_at = now or datetime.now(UTC)
    rows: list[StandardsSourceRegistry] = []
    for definition in DEFAULT_STANDARDS_SOURCES:
        _validate_source_uri(definition.source_uri)
        row = db.get(StandardsSourceRegistry, definition.source_id)
        if row is None:
            row = StandardsSourceRegistry(
                source_id=definition.source_id,
                display_name=definition.display_name,
                source_owner=definition.source_owner,
                source_uri=definition.source_uri,
                source_format=definition.source_format,
                source_scope=definition.source_scope,
                parser_version=definition.parser_version,
                review_interval_hours=definition.review_interval_hours,
                is_active=True,
                created_at=observed_at,
                updated_at=observed_at,
            )
            db.add(row)
        else:
            row.display_name = definition.display_name
            row.source_owner = definition.source_owner
            row.source_uri = definition.source_uri
            row.source_format = definition.source_format
            row.source_scope = definition.source_scope
            row.parser_version = definition.parser_version
            row.review_interval_hours = definition.review_interval_hours
            row.updated_at = observed_at
        rows.append(row)
    db.flush()
    if commit:
        db.commit()
    return rows


def check_source(
    db: Session,
    *,
    source_id: str,
    timeout_seconds: float = 15.0,
    max_content_bytes: int = DEFAULT_MAX_CONTENT_BYTES,
    client: httpx.Client | None = None,
    now: datetime | None = None,
    commit: bool = True,
) -> dict[str, Any]:
    source = db.get(StandardsSourceRegistry, source_id)
    if source is None or not source.is_active:
        raise ValueError("Standards source is unknown or inactive.")
    _validate_source_uri(source.source_uri)
    observed_at = now or datetime.now(UTC)
    latest = _latest_snapshot(db, source_id=source.source_id)
    headers = {
        "Accept": "application/json, application/atom+xml, application/rss+xml, text/html, text/plain",
        "User-Agent": "InsightOS-Standards-Monitor/1.0",
    }
    if latest is not None and latest.etag:
        headers["If-None-Match"] = latest.etag
    if latest is not None and latest.last_modified:
        headers["If-Modified-Since"] = latest.last_modified

    owns_client = client is None
    resolved_client = client or httpx.Client(
        timeout=timeout_seconds,
        follow_redirects=True,
    )
    try:
        response = resolved_client.get(source.source_uri, headers=headers)
        _validate_source_uri(str(response.url))
        if response.status_code == 304:
            _record_success(
                source,
                observed_at=observed_at,
                http_status=304,
                source_digest=latest.source_digest if latest is not None else None,
                normalized_digest=latest.normalized_digest if latest is not None else None,
            )
            if commit:
                db.commit()
            return _check_result(source, latest, change_status="not_modified", snapshot_created=False)

        response.raise_for_status()
        content = bytes(response.content)
        if not content:
            raise ValueError("The official source returned an empty response.")
        if len(content) > max(1, int(max_content_bytes)):
            raise ValueError("The official source response exceeded the configured evidence limit.")

        content_type = str(response.headers.get("content-type") or "").strip() or None
        content_text = content.decode(response.encoding or "utf-8", errors="replace")
        normalized_text = _normalize_content(
            content_text,
            source_format=source.source_format,
        )
        source_digest = sha256(content).hexdigest()
        normalized_digest = sha256(normalized_text.encode("utf-8")).hexdigest()
        existing = (
            db.query(StandardsSourceSnapshot)
            .filter(
                StandardsSourceSnapshot.source_id == source.source_id,
                StandardsSourceSnapshot.source_digest == source_digest,
            )
            .one_or_none()
        )
        snapshot_created = existing is None
        previous_digest = source.last_source_digest
        if existing is None:
            existing = StandardsSourceSnapshot(
                source_id=source.source_id,
                source_uri=str(response.url),
                source_format=source.source_format,
                parser_version=source.parser_version,
                http_status=response.status_code,
                content_type=content_type,
                etag=response.headers.get("etag"),
                last_modified=response.headers.get("last-modified"),
                source_digest=source_digest,
                normalized_digest=normalized_digest,
                content_bytes=len(content),
                content_text=content_text,
                observed_at=observed_at,
            )
            db.add(existing)
        _record_success(
            source,
            observed_at=observed_at,
            http_status=response.status_code,
            source_digest=source_digest,
            normalized_digest=normalized_digest,
        )
        db.flush()
        candidate: StandardsChangeCandidate | None = None
        if (
            snapshot_created
            and latest is not None
            and latest.normalized_digest != normalized_digest
        ):
            candidate = create_change_candidate(
                db,
                source=source,
                previous_snapshot=latest,
                current_snapshot=existing,
                now=observed_at,
                commit=False,
            )
            db.flush()
        if commit:
            db.commit()
        change_status = "initial_snapshot" if previous_digest is None else "unchanged"
        if previous_digest is not None and previous_digest != source_digest:
            change_status = "changed"
        return _check_result(
            source,
            existing,
            change_status=change_status,
            snapshot_created=snapshot_created,
            candidate=candidate,
        )
    except Exception as exc:
        db.rollback()
        source = db.get(StandardsSourceRegistry, source_id)
        if source is None:
            raise
        _record_failure(source, observed_at=observed_at, error=exc)
        db.flush()
        if commit:
            db.commit()
        return {
            "source_id": source.source_id,
            "status": "check_failed",
            "checked_at": source.last_checked_at,
            "error_code": source.last_error_code,
            "error_message": source.last_error_message,
            "automatic_activation_allowed": False,
        }
    finally:
        if owns_client:
            resolved_client.close()


def list_source_status(db: Session) -> dict[str, Any]:
    rows = (
        db.query(StandardsSourceRegistry)
        .order_by(StandardsSourceRegistry.source_scope, StandardsSourceRegistry.source_id)
        .all()
    )
    items: list[dict[str, Any]] = []
    for row in rows:
        snapshot_count = (
            db.query(StandardsSourceSnapshot)
            .filter(StandardsSourceSnapshot.source_id == row.source_id)
            .count()
        )
        items.append(
            {
                "source_id": row.source_id,
                "display_name": row.display_name,
                "source_owner": row.source_owner,
                "source_uri": row.source_uri,
                "source_format": row.source_format,
                "source_scope": row.source_scope,
                "parser_version": row.parser_version,
                "review_interval_hours": row.review_interval_hours,
                "is_active": row.is_active,
                "last_checked_at": row.last_checked_at,
                "last_success_at": row.last_success_at,
                "last_http_status": row.last_http_status,
                "last_source_digest": row.last_source_digest,
                "last_normalized_digest": row.last_normalized_digest,
                "last_error_code": row.last_error_code,
                "last_error_message": row.last_error_message,
                "snapshot_count": snapshot_count,
            }
        )
    checked = sum(1 for item in items if item["last_checked_at"] is not None)
    has_errors = any(item["last_error_code"] is not None for item in items)
    status = "healthy"
    if has_errors or not items:
        status = "attention_required"
    elif checked < len(items):
        status = "pending_initial_check"
    blocking_changes = (
        db.query(StandardsChangeCandidate)
        .filter(StandardsChangeCandidate.status.in_(BLOCKING_CANDIDATE_STATUSES))
        .count()
    )
    if blocking_changes:
        status = "attention_required"
    return {
        "status": status,
        "registered_sources": len(items),
        "checked_sources": checked,
        "blocking_change_candidates": blocking_changes,
        "items": items,
        "automatic_activation_allowed": False,
    }


def create_change_candidate(
    db: Session,
    *,
    source: StandardsSourceRegistry,
    previous_snapshot: StandardsSourceSnapshot,
    current_snapshot: StandardsSourceSnapshot,
    now: datetime | None = None,
    commit: bool = True,
) -> StandardsChangeCandidate:
    existing = (
        db.query(StandardsChangeCandidate)
        .filter(
            StandardsChangeCandidate.source_id == source.source_id,
            StandardsChangeCandidate.current_snapshot_id == current_snapshot.id,
        )
        .one_or_none()
    )
    if existing is not None:
        return existing

    previous_text = _normalize_content(
        previous_snapshot.content_text,
        source_format=previous_snapshot.source_format,
    )
    current_text = _normalize_content(
        current_snapshot.content_text,
        source_format=current_snapshot.source_format,
    )
    diff = _deterministic_diff(previous_text, current_text)
    classified = _classify_change(source, diff)
    observed_at = now or datetime.now(UTC)
    candidate = StandardsChangeCandidate(
        source_id=source.source_id,
        previous_snapshot_id=previous_snapshot.id,
        current_snapshot_id=current_snapshot.id,
        classification_version=CLASSIFICATION_VERSION,
        change_type=classified.change_type,
        materiality=classified.materiality,
        status=classified.status,
        title=classified.title,
        summary=classified.summary,
        diff_json=json.dumps(diff, sort_keys=True, ensure_ascii=False),
        classification_reasons_json=json.dumps(
            list(classified.reasons), sort_keys=True, ensure_ascii=False
        ),
        automatic_activation_allowed=False,
        created_at=observed_at,
        updated_at=observed_at,
    )
    db.add(candidate)
    db.flush()
    for impact in _impact_specs(source, classified):
        db.add(
            StandardsImpactLink(
                candidate_id=candidate.id,
                impact_type=impact["impact_type"],
                impact_key=impact["impact_key"],
                impact_reason=impact["impact_reason"],
                risk_state=impact["risk_state"],
                is_blocking=impact["is_blocking"],
                created_at=observed_at,
            )
        )
    db.flush()
    if commit:
        db.commit()
        db.refresh(candidate)
    return candidate


def list_change_candidates(
    db: Session,
    *,
    status_filter: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    query = db.query(StandardsChangeCandidate)
    if status_filter:
        query = query.filter(StandardsChangeCandidate.status == status_filter.strip())
    rows = (
        query.order_by(
            StandardsChangeCandidate.created_at.desc(),
            StandardsChangeCandidate.id.desc(),
        )
        .limit(max(1, min(int(limit), 250)))
        .all()
    )
    items = [_candidate_payload(db, row, include_diff=False) for row in rows]
    return {
        "status": (
            "attention_required"
            if any(item["blocks_provider_collection"] for item in items)
            else "current"
        ),
        "items": items,
        "returned": len(items),
        "automatic_activation_allowed": False,
    }


def get_change_candidate(db: Session, candidate_id: str) -> dict[str, Any] | None:
    row = db.get(StandardsChangeCandidate, candidate_id)
    if row is None:
        return None
    return _candidate_payload(db, row, include_diff=True)


def review_change_candidate(
    db: Session,
    *,
    candidate_id: str,
    disposition: str,
    actor_user_id: str,
    note: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    resolved_disposition = disposition.strip()
    if resolved_disposition not in REVIEW_DISPOSITIONS:
        raise ValueError("Choose a supported standards-change review disposition.")
    row = db.get(StandardsChangeCandidate, candidate_id)
    if row is None:
        raise ValueError("Standards change candidate was not found.")
    reviewed_at = now or datetime.now(UTC)
    if resolved_disposition == "reopen":
        row.status = "needs_review"
        row.review_disposition = None
        row.review_note = None
        row.reviewed_by_user_id = None
        row.reviewed_at = None
    else:
        row.status = resolved_disposition
        row.review_disposition = resolved_disposition
        row.review_note = (note or "").strip()[:4000] or None
        row.reviewed_by_user_id = actor_user_id
        row.reviewed_at = reviewed_at
    row.updated_at = reviewed_at
    row.automatic_activation_allowed = False
    db.commit()
    db.refresh(row)
    return _candidate_payload(db, row, include_diff=True)


def assert_provider_contract_ready(db: Session, adapter_key: str) -> None:
    resolved_key = adapter_key.strip()
    blocking = (
        db.query(StandardsImpactLink, StandardsChangeCandidate)
        .join(
            StandardsChangeCandidate,
            StandardsChangeCandidate.id == StandardsImpactLink.candidate_id,
        )
        .filter(
            StandardsImpactLink.impact_type == "provider_adapter",
            StandardsImpactLink.impact_key == resolved_key,
            StandardsImpactLink.is_blocking.is_(True),
            StandardsChangeCandidate.status.in_(BLOCKING_CANDIDATE_STATUSES),
        )
        .order_by(StandardsChangeCandidate.created_at.desc())
        .first()
    )
    if blocking is not None:
        _impact, candidate = blocking
        raise StandardsContractBlockedError(resolved_key, candidate.id)


def _candidate_payload(
    db: Session,
    row: StandardsChangeCandidate,
    *,
    include_diff: bool,
) -> dict[str, Any]:
    impacts = (
        db.query(StandardsImpactLink)
        .filter(StandardsImpactLink.candidate_id == row.id)
        .order_by(StandardsImpactLink.impact_type, StandardsImpactLink.impact_key)
        .all()
    )
    payload: dict[str, Any] = {
        "id": row.id,
        "source_id": row.source_id,
        "previous_snapshot_id": row.previous_snapshot_id,
        "current_snapshot_id": row.current_snapshot_id,
        "classification_version": row.classification_version,
        "change_type": row.change_type,
        "materiality": row.materiality,
        "status": row.status,
        "title": row.title,
        "summary": row.summary,
        "classification_reasons": _json_list(row.classification_reasons_json),
        "automatic_activation_allowed": False,
        "review_disposition": row.review_disposition,
        "review_note": row.review_note,
        "reviewed_by_user_id": row.reviewed_by_user_id,
        "reviewed_at": row.reviewed_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "blocks_provider_collection": any(
            impact.is_blocking and row.status in BLOCKING_CANDIDATE_STATUSES
            for impact in impacts
        ),
        "impacts": [
            {
                "id": impact.id,
                "impact_type": impact.impact_type,
                "impact_key": impact.impact_key,
                "impact_reason": impact.impact_reason,
                "risk_state": impact.risk_state,
                "is_blocking": impact.is_blocking,
            }
            for impact in impacts
        ],
    }
    if include_diff:
        payload["diff"] = _json_dict(row.diff_json)
    return payload


def _deterministic_diff(previous_text: str, current_text: str) -> dict[str, Any]:
    previous_tokens = _diff_tokens(previous_text)
    current_tokens = _diff_tokens(current_text)
    matcher = SequenceMatcher(a=previous_tokens, b=current_tokens, autojunk=False)
    added: list[str] = []
    removed: list[str] = []
    context: list[str] = []
    for opcode, previous_start, previous_end, current_start, current_end in matcher.get_opcodes():
        if opcode in {"replace", "delete"} and previous_start != previous_end:
            removed.append(_render_diff_tokens(previous_tokens[previous_start:previous_end]))
        if opcode in {"replace", "insert"} and current_start != current_end:
            added.append(_render_diff_tokens(current_tokens[current_start:current_end]))
        if opcode != "equal":
            current_context = current_tokens[
                max(0, current_start - 8) : min(len(current_tokens), current_end + 8)
            ]
            previous_context = previous_tokens[
                max(0, previous_start - 8) : min(len(previous_tokens), previous_end + 8)
            ]
            context.append(
                _render_diff_tokens(current_context or previous_context)
            )
    return {
        "added": [value for value in added[:50] if value],
        "removed": [value for value in removed[:50] if value],
        "context": [value for value in context[:50] if value],
        "previous_normalized_digest": sha256(previous_text.encode("utf-8")).hexdigest(),
        "current_normalized_digest": sha256(current_text.encode("utf-8")).hexdigest(),
    }


def _diff_tokens(value: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9_.:/%+\-]+|[^\w\s]", value, flags=re.UNICODE)


def _render_diff_tokens(tokens: list[str]) -> str:
    rendered = " ".join(tokens[:120])
    rendered = re.sub(r"\s+([,.;:!?\]\)])", r"\1", rendered)
    rendered = re.sub(r"([\[\(])\s+", r"\1", rendered)
    return rendered.strip()[:2000]


def _classify_change(
    source: StandardsSourceRegistry,
    diff: dict[str, Any],
) -> ClassifiedStandardsChange:
    delta_text = " ".join(
        str(value)
        for key in ("added", "removed", "context")
        for value in diff.get(key, [])
    ).lower()
    reasons: list[str] = []
    change_type = "unclassified_change"
    materiality = "unknown"

    if source.source_scope == "search_status":
        change_type = "incident_or_status_change"
        materiality = "material"
        reasons.append("The source is Google's Search status incident feed.")
    elif re.search(r"\b(deprecat(?:e|ed|ion)|sunset|removed?|retired?|endpoint|field)\b", delta_text):
        change_type = "api_field_or_deprecation_change"
        materiality = "material"
        reasons.append("The changed text contains an API field, endpoint, removal, or deprecation signal.")
    elif re.search(
        r"\b(threshold|boundary|good|poor|needs improvement|p75|percentile)\b|"
        r"\b\d+(?:\.\d+)?\s*(?:ms|milliseconds?|s|seconds?|%|percent|days?|hours?)\b",
        delta_text,
    ):
        change_type = "threshold_change"
        materiality = "material"
        reasons.append("The changed text contains a governed threshold or measurement boundary.")
    elif re.search(
        r"\b(metric|definition|aggregation|dimension|clicks?|impressions?|ctr|position|"
        r"direction requests?|bookings?|search terms?)\b",
        delta_text,
    ):
        change_type = "metric_definition_change"
        materiality = "material"
        reasons.append("The changed text affects a named measurement, dimension, or aggregation.")
    elif re.search(
        r"\b(policy|policies|prohibited|eligib(?:le|ility)|requirement|violation|"
        r"must not|may not|not allowed)\b",
        delta_text,
    ):
        change_type = "policy_change"
        materiality = "material"
        reasons.append("The changed text contains a policy, eligibility, or prohibited-action signal.")
    elif source.source_id in {
        "google.search.ranking_systems",
        "google.business.local_ranking",
    } or re.search(r"\b(ranking system|local ranking|relevance|distance|prominence)\b", delta_text):
        change_type = "ranking_system_guidance"
        materiality = "material"
        reasons.append("The change is in published ranking-system or local-ranking guidance.")
    elif re.search(r"\b(typo|formatting|editorial|wording|example only|clarif(?:y|ied))\b", delta_text):
        change_type = "editorial_only_change"
        materiality = "editorial"
        reasons.append("The changed text explicitly describes an editorial or wording-only update.")
    else:
        reasons.append("No approved deterministic rule could safely classify the changed meaning.")

    status = "editorial_only" if materiality == "editorial" else "needs_review"
    labels = {
        "threshold_change": "Published measurement boundary changed",
        "metric_definition_change": "Published measurement definition changed",
        "api_field_or_deprecation_change": "Published API contract changed",
        "ranking_system_guidance": "Published ranking guidance changed",
        "policy_change": "Published Google policy changed",
        "incident_or_status_change": "Google reported a Search status change",
        "editorial_only_change": "Published wording changed",
        "unclassified_change": "Published source changed and needs review",
    }
    title = labels[change_type]
    summary = (
        f"{source.display_name} changed. InsightOS classified the saved diff as "
        f"{title.lower()}. Production rules remain unchanged until a platform review."
    )
    return ClassifiedStandardsChange(
        change_type=change_type,
        materiality=materiality,
        status=status,
        title=title,
        summary=summary,
        reasons=tuple(reasons),
    )


def _impact_specs(
    source: StandardsSourceRegistry,
    classified: ClassifiedStandardsChange,
) -> list[dict[str, Any]]:
    specs: dict[tuple[str, str], str] = {}

    def add(impact_type: str, impact_key: str, reason: str) -> None:
        specs[(impact_type, impact_key)] = reason

    scope = source.source_scope
    if scope == "website_measurements":
        metric_key = (
            "core_web_vitals" if "core_web_vitals" in source.source_id else "structured_data"
        )
        add("metric_contract", metric_key, "Website measurements use this published definition.")
        add("action_contract", "website_actions", "Website actions may reference this guidance.")
        add("ui_label", "website_health", "Customer explanations may use this definition.")
        add("forecast", "website_improvement", "Forecast boundaries may depend on this metric.")
        add("historical_comparison", metric_key, "Existing comparisons may need a version boundary.")
    elif scope == "search_console_metrics":
        add("provider_adapter", "google_search_console", "Search Console fields must retain verified meanings.")
        add("metric_contract", "search_console_performance", "Clicks, impressions, CTR, and position use this source.")
        add("action_contract", "search_visibility_actions", "Search actions use these measurements.")
        add("report", "search_performance", "Reports display these measurements.")
        add("historical_comparison", "search_console_performance", "Definition changes can invalidate comparisons.")
    elif scope in {"business_profile_api", "business_profile_metrics"}:
        add("provider_adapter", "google_business_profile", "The Business Profile adapter must match the published contract.")
        add("metric_contract", "business_profile_performance", "Profile measurements use this API contract.")
        add("action_contract", "business_profile_actions", "Profile actions use these fields and measurements.")
        add("ui_label", "local_visibility", "Local Search displays these measurements.")
        add("report", "business_profile_performance", "Reports may display these measurements.")
        add("historical_comparison", "business_profile_performance", "Definition changes can require a new baseline.")
    elif scope == "business_profile_guidance":
        add("lexicon_rule", "local_search_guidance", "Local recommendations use this published guidance.")
        add("action_contract", "business_profile_actions", "Profile actions may be affected.")
        add("ui_label", "local_visibility", "Customer explanations may need review.")
    elif scope == "search_guidance":
        add("lexicon_rule", "google_search_guidance", "Diagnostics use this published guidance.")
        add("action_contract", "website_actions", "Website recommendations may be affected.")
        add("ui_label", "website_health", "Customer explanations may need review.")
    elif scope == "search_status":
        add("operator_alert", "google_search_status", "A provider incident may explain shared movement.")
        add("report", "search_status_context", "Reports may need incident context.")

    if classified.change_type == "unclassified_change":
        add("operator_alert", source.source_id, "The meaning is unknown and requires platform review.")
    if classified.change_type == "policy_change":
        add("action_contract", "governed_actions", "Policy changes require action-safety review.")
    if classified.change_type == "api_field_or_deprecation_change" and not any(
        impact_type == "provider_adapter" for impact_type, _impact_key in specs
    ):
        add("provider_adapter", source.source_id, "An API contract change must fail closed.")

    blocking_change_types = {
        "threshold_change",
        "metric_definition_change",
        "api_field_or_deprecation_change",
        "policy_change",
        "unclassified_change",
    }
    rows: list[dict[str, Any]] = []
    for (impact_type, impact_key), reason in sorted(specs.items()):
        is_blocking = (
            classified.materiality != "editorial"
            and classified.change_type in blocking_change_types
            and impact_type in {"provider_adapter", "metric_contract", "action_contract"}
        )
        rows.append(
            {
                "impact_type": impact_type,
                "impact_key": impact_key,
                "impact_reason": reason,
                "risk_state": "fail_closed" if is_blocking else "review_required",
                "is_blocking": is_blocking,
            }
        )
    return rows


def _json_list(value: str) -> list[Any]:
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def _json_dict(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _latest_snapshot(db: Session, *, source_id: str) -> StandardsSourceSnapshot | None:
    return (
        db.query(StandardsSourceSnapshot)
        .filter(StandardsSourceSnapshot.source_id == source_id)
        .order_by(
            StandardsSourceSnapshot.observed_at.desc(),
            StandardsSourceSnapshot.id.desc(),
        )
        .first()
    )


def _validate_source_uri(uri: str) -> None:
    parsed = urlparse(uri)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_SOURCE_HOSTS:
        raise ValueError("Standards sources must use an approved official Google HTTPS host.")
    if parsed.username or parsed.password:
        raise ValueError("Standards source URLs cannot contain credentials.")


def _normalize_content(content_text: str, *, source_format: str) -> str:
    if source_format == "json":
        parsed = json.loads(content_text)
        return json.dumps(parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    if source_format == "html":
        parser = _VisibleTextParser()
        parser.feed(content_text)
        content_text = " ".join(parser.parts)
    return re.sub(r"\s+", " ", content_text).strip()


def _record_success(
    source: StandardsSourceRegistry,
    *,
    observed_at: datetime,
    http_status: int,
    source_digest: str | None,
    normalized_digest: str | None,
) -> None:
    source.last_checked_at = observed_at
    source.last_success_at = observed_at
    source.last_http_status = http_status
    source.last_source_digest = source_digest
    source.last_normalized_digest = normalized_digest
    source.last_error_code = None
    source.last_error_message = None
    source.updated_at = observed_at


def _record_failure(
    source: StandardsSourceRegistry,
    *,
    observed_at: datetime,
    error: Exception,
) -> None:
    source.last_checked_at = observed_at
    source.last_http_status = (
        error.response.status_code if isinstance(error, httpx.HTTPStatusError) else None
    )
    source.last_error_code = _error_code(error)
    source.last_error_message = str(error)[:1000]
    source.updated_at = observed_at


def _error_code(error: Exception) -> str:
    if isinstance(error, httpx.TimeoutException):
        return "source_timeout"
    if isinstance(error, httpx.HTTPStatusError):
        return "source_http_error"
    if isinstance(error, httpx.RequestError):
        return "source_request_error"
    if isinstance(error, json.JSONDecodeError):
        return "source_parse_error"
    if isinstance(error, ValueError):
        return "source_validation_error"
    return "source_check_error"


def _check_result(
    source: StandardsSourceRegistry,
    snapshot: StandardsSourceSnapshot | None,
    *,
    change_status: str,
    snapshot_created: bool,
    candidate: StandardsChangeCandidate | None = None,
) -> dict[str, Any]:
    return {
        "source_id": source.source_id,
        "status": "current" if change_status in {"unchanged", "not_modified"} else change_status,
        "change_status": change_status,
        "checked_at": source.last_checked_at,
        "last_success_at": source.last_success_at,
        "http_status": source.last_http_status,
        "source_digest": source.last_source_digest,
        "normalized_digest": source.last_normalized_digest,
        "snapshot_id": snapshot.id if snapshot is not None else None,
        "snapshot_created": snapshot_created,
        "change_candidate_id": candidate.id if candidate is not None else None,
        "change_candidate_status": candidate.status if candidate is not None else None,
        "change_type": candidate.change_type if candidate is not None else None,
        "automatic_activation_allowed": False,
    }
