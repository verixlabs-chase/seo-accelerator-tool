from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.intelligence.executors import wordpress_plugin
from app.models.recommendation_execution import RecommendationExecution
from app.models.wordpress_change_preview import WordPressChangePreview


WORDPRESS_MUTATION_EXECUTION_TYPES = {
    "create_content_brief",
    "fix_missing_title",
    "improve_internal_links",
    "publish_schema_markup",
}


class WordPressChangePreviewError(RuntimeError):
    def __init__(self, message: str, *, reason_code: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


def requires_wordpress_preview(execution: RecommendationExecution) -> bool:
    return execution.execution_type in WORDPRESS_MUTATION_EXECUTION_TYPES


def create_change_preview(
    db: Session,
    *,
    execution: RecommendationExecution,
    planned_result: dict[str, Any],
) -> dict[str, Any]:
    mutations = planned_result.get("mutations")
    if not isinstance(mutations, list) or not mutations:
        return planned_result

    try:
        delivery = wordpress_plugin.preview_mutations(db, execution=execution, mutations=mutations)
    except wordpress_plugin.WordPressExecutionError as exc:
        raise WordPressChangePreviewError(str(exc), reason_code=exc.reason_code) from exc
    changes = [item for item in delivery.get("results", []) if isinstance(item, dict)]
    conflicts = [
        conflict
        for item in changes
        for conflict in (item.get("conflicts") or [])
        if isinstance(conflict, dict)
    ]
    affected_urls = sorted(
        {
            str(item.get("target_url") or "")
            for item in changes
            if str(item.get("target_url") or "").strip()
        }
    )
    snapshot = {
        "execution_id": execution.id,
        "recommendation_id": execution.recommendation_id,
        "campaign_id": execution.campaign_id,
        "status": "blocked" if conflicts else "ready",
        "approval_required": True,
        "affected_urls": affected_urls,
        "mutation_count": len(changes),
        "conflict_count": len(conflicts),
        "changes": changes,
        "conflicts": conflicts,
        "rollback_summary": (
            "InsightOS will save the current WordPress values before applying each approved change. "
            "Those saved values are used to reverse the change if needed."
        ),
        "created_at": datetime.now(UTC).isoformat(),
    }
    preview_hash = _preview_hash(snapshot)
    snapshot["preview_hash"] = preview_hash

    existing = (
        db.query(WordPressChangePreview)
        .filter(
            WordPressChangePreview.execution_id == execution.id,
            WordPressChangePreview.preview_hash == preview_hash,
        )
        .first()
    )
    if existing is None:
        prior_rows = (
            db.query(WordPressChangePreview)
            .filter(
                WordPressChangePreview.execution_id == execution.id,
                WordPressChangePreview.status.in_(["ready", "approved"]),
            )
            .all()
        )
        for row in prior_rows:
            row.status = "superseded"
        if prior_rows:
            execution.approved_by = None
            execution.approved_at = None
            if execution.status == "scheduled":
                execution.status = "pending"
        existing = WordPressChangePreview(
            tenant_id=_tenant_id_from_payload(execution),
            campaign_id=execution.campaign_id,
            execution_id=execution.id,
            recommendation_id=execution.recommendation_id,
            preview_hash=preview_hash,
            status="blocked" if conflicts else "ready",
            snapshot=snapshot,
            affected_url_count=len(affected_urls),
            mutation_count=len(changes),
            conflict_count=len(conflicts),
            approval_required=True,
        )
        db.add(existing)
        db.flush()

    planned_result["preview"] = serialize_preview(existing)
    planned_result["notes"] = (
        "The proposed WordPress changes were checked without changing the website."
        if not conflicts
        else "The website was not changed because the preview found an issue that needs attention."
    )
    return planned_result


def approve_change_preview(
    db: Session,
    *,
    execution: RecommendationExecution,
    preview_hash: str | None,
    approved_by: str,
) -> WordPressChangePreview:
    if not preview_hash:
        raise WordPressChangePreviewError(
            "Preview the exact website changes before approving them.",
            reason_code="wordpress_preview_required",
        )
    row = (
        db.query(WordPressChangePreview)
        .filter(
            WordPressChangePreview.execution_id == execution.id,
            WordPressChangePreview.preview_hash == preview_hash,
        )
        .first()
    )
    if row is None or row.status == "superseded":
        raise WordPressChangePreviewError(
            "That preview is no longer current. Check the website changes again.",
            reason_code="wordpress_preview_stale",
        )
    if row.status == "blocked" or row.conflict_count:
        raise WordPressChangePreviewError(
            "This preview found a conflict. Resolve it and check the changes again before approval.",
            reason_code="wordpress_preview_conflict",
        )
    row.status = "approved"
    row.approved_by = approved_by
    row.approved_at = datetime.now(UTC)
    db.flush()
    return row


def bind_approved_preview(
    db: Session,
    *,
    execution: RecommendationExecution,
    mutations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    row = (
        db.query(WordPressChangePreview)
        .filter(
            WordPressChangePreview.execution_id == execution.id,
            WordPressChangePreview.status == "approved",
        )
        .order_by(WordPressChangePreview.approved_at.desc(), WordPressChangePreview.created_at.desc())
        .first()
    )
    if row is None:
        raise WordPressChangePreviewError(
            "Preview and approve the exact website changes before running them.",
            reason_code="wordpress_preview_approval_required",
        )
    snapshot = row.snapshot if isinstance(row.snapshot, dict) else {}
    expected_by_mutation = {
        str(item.get("mutation_id") or ""): item.get("expected_version")
        for item in (snapshot.get("changes") or [])
        if isinstance(item, dict)
    }
    bound: list[dict[str, Any]] = []
    for mutation in mutations:
        mutation_id = str(mutation.get("mutation_id") or "")
        expected_version = expected_by_mutation.get(mutation_id)
        if not isinstance(expected_version, dict) or not expected_version:
            raise WordPressChangePreviewError(
                "The approved preview does not match every planned website change. Check the changes again.",
                reason_code="wordpress_preview_incomplete",
            )
        bound.append({**mutation, "expected_version": expected_version})
    return bound


def serialize_preview(row: WordPressChangePreview) -> dict[str, Any]:
    snapshot = dict(row.snapshot if isinstance(row.snapshot, dict) else {})
    snapshot.update(
        {
            "id": row.id,
            "preview_hash": row.preview_hash,
            "status": row.status,
            "approved_by": row.approved_by,
            "approved_at": row.approved_at.isoformat() if row.approved_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else snapshot.get("created_at"),
        }
    )
    return snapshot


def _preview_hash(snapshot: dict[str, Any]) -> str:
    canonical = dict(snapshot)
    canonical.pop("created_at", None)
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _tenant_id_from_payload(execution: RecommendationExecution) -> str:
    try:
        payload = json.loads(execution.execution_payload or "{}")
    except json.JSONDecodeError as exc:
        raise WordPressChangePreviewError(
            "The saved execution details are invalid.",
            reason_code="wordpress_preview_payload_invalid",
        ) from exc
    tenant_id = str(payload.get("tenant_id") or "") if isinstance(payload, dict) else ""
    if not tenant_id:
        raise WordPressChangePreviewError(
            "The saved execution is missing its workspace scope.",
            reason_code="wordpress_preview_tenant_missing",
        )
    return tenant_id
