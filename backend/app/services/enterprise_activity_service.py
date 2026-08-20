from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings
from app.models.audit_log import AuditLog
from app.models.user import User
from app.services.commercial_plan_service import (
    FEATURE_ORGANIZATION_ACTIVITY,
    require_commercial_feature,
)


@dataclass(frozen=True)
class ActivityDefinition:
    kind: str
    category: str
    title: str
    summary: str
    tone: str = "neutral"


CATEGORY_LABELS = {
    "reports": "Reports and exports",
    "automations": "Workflow connections",
    "content": "Content and publishing",
    "connections": "Connected services",
    "team": "Team access",
    "workspace": "Workspace and billing",
    "reviews": "Customer reviews",
}


EVENT_CATALOG: dict[str, ActivityDefinition] = {
    "enterprise.report_branding.updated": ActivityDefinition(
        "report_branding_updated", "reports", "Report identity changed",
        "Future reports will use the updated report identity.",
    ),
    "enterprise.report_branding.logo_updated": ActivityDefinition(
        "report_logo_updated", "reports", "Report logo changed",
        "Future reports can use the newly verified logo.",
    ),
    "enterprise.report_branding.logo_removed": ActivityDefinition(
        "report_logo_removed", "reports", "Saved report logo removed",
        "Older reports keep their frozen logo; future reports will not use the removed file.",
    ),
    "enterprise.client_report_package.downloaded": ActivityDefinition(
        "client_report_package_downloaded", "reports", "Client report package downloaded",
        "A verified package of saved location reports was downloaded.", "positive",
    ),
    "report.share_link.created": ActivityDefinition(
        "private_report_link_created", "reports", "Private report link created",
        "A time-limited client report link was created.",
    ),
    "report.share_link.opened": ActivityDefinition(
        "private_report_link_opened", "reports", "Private report first opened",
        "A private client report link was used for the first time.", "positive",
    ),
    "report.share_link.revoked": ActivityDefinition(
        "private_report_link_revoked", "reports", "Private report link turned off",
        "A private client report link was turned off before or after its expiration.",
    ),
    "governance.data_export.ready": ActivityDefinition(
        "account_export_ready", "reports", "Account export prepared",
        "A portable account copy was prepared for the workspace.", "positive",
    ),
    "governance.data_export.downloaded": ActivityDefinition(
        "account_export_downloaded", "reports", "Account export downloaded",
        "A prepared account copy was downloaded.", "positive",
    ),
    "governance.data_export.failed": ActivityDefinition(
        "account_export_failed", "reports", "Account export needs attention",
        "The requested account copy could not be prepared.", "attention",
    ),
    "automation.webhook_connection.created": ActivityDefinition(
        "workflow_connection_created", "automations", "Workflow connection added",
        "A new outside workflow destination was saved.",
    ),
    "automation.webhook_connection.secret_rotated": ActivityDefinition(
        "workflow_secret_rotated", "automations", "Workflow signing key replaced",
        "The old signing key can no longer authenticate new deliveries.",
    ),
    "automation.webhook_connection.paused": ActivityDefinition(
        "workflow_connection_paused", "automations", "Workflow connection paused",
        "New automatic updates to this destination were paused.", "attention",
    ),
    "automation.webhook_connection.resumed": ActivityDefinition(
        "workflow_connection_resumed", "automations", "Workflow connection resumed",
        "Eligible automatic updates can use this destination again.", "positive",
    ),
    "automation.webhook_connection.disconnected": ActivityDefinition(
        "workflow_connection_disconnected", "automations", "Workflow connection removed",
        "New automatic updates will not use the removed destination.",
    ),
    "automation.service_account.created": ActivityDefinition(
        "workflow_access_created", "automations", "Workflow access created",
        "A limited workflow key was created with saved permissions.",
    ),
    "automation.service_account.rotated": ActivityDefinition(
        "workflow_access_rotated", "automations", "Workflow access key replaced",
        "The previous workflow key can no longer request new work.",
    ),
    "automation.service_account.revoked": ActivityDefinition(
        "workflow_access_revoked", "automations", "Workflow access removed",
        "The revoked workflow key can no longer request new work.",
    ),
    "automation.webhook_delivery.failed": ActivityDefinition(
        "workflow_delivery_failed", "automations", "Workflow update needs attention",
        "An outside workflow destination did not accept an update.", "attention",
    ),
    "automation.webhook_delivery.recovered": ActivityDefinition(
        "workflow_delivery_retried", "automations", "Workflow update retried",
        "A failed workflow update was placed back into the retry process.",
    ),
    "content.brief.reviewed": ActivityDefinition(
        "content_brief_reviewed", "content", "Content brief reviewed",
        "A team decision was saved for a content brief.",
    ),
    "content.draft.created": ActivityDefinition(
        "content_draft_created", "content", "Working draft created",
        "An approved brief was turned into an editable working draft.",
    ),
    "content.draft.saved": ActivityDefinition(
        "content_draft_saved", "content", "Working draft saved",
        "Changes to a private working draft were saved.",
    ),
    "content.publishing_handoff.prepared": ActivityDefinition(
        "publishing_preview_prepared", "content", "Website change preview prepared",
        "An exact website change preview was prepared for review.",
    ),
    "content.publishing_handoff.approved": ActivityDefinition(
        "publishing_preview_approved", "content", "Website change approved",
        "A reviewed website change was explicitly approved.",
    ),
    "content.publishing_handoff.delivered": ActivityDefinition(
        "publishing_change_delivered", "content", "Website change completed",
        "An approved website change reached the connected site.", "positive",
    ),
    "wordpress.site.pairing_started": ActivityDefinition(
        "wordpress_pairing_started", "connections", "Website connection started",
        "A team member started connecting a WordPress website.",
    ),
    "wordpress.site.paired": ActivityDefinition(
        "wordpress_connected", "connections", "WordPress website connected",
        "A WordPress website completed its connection check.", "positive",
    ),
    "wordpress.site.disconnected": ActivityDefinition(
        "wordpress_disconnected", "connections", "WordPress website disconnected",
        "InsightOS can no longer send new approved changes to that website.",
    ),
    "governance.provider_disconnected": ActivityDefinition(
        "google_disconnected", "connections", "Google connection removed",
        "The outside Google connection was removed while saved results were preserved.",
    ),
    "portfolio.access_grant.created": ActivityDefinition(
        "team_access_created", "team", "Team access added",
        "A team member received saved access to selected locations.",
    ),
    "portfolio.access_grant.updated": ActivityDefinition(
        "team_access_updated", "team", "Team access changed",
        "A team member's saved location access was changed.",
    ),
    "portfolio.access_grant.revoked": ActivityDefinition(
        "team_access_revoked", "team", "Team access removed",
        "A team member's saved location access was removed.",
    ),
    "migration.import.applied": ActivityDefinition(
        "migration_imported", "workspace", "Previous SEO data imported",
        "Reviewed records from a previous system were added to this workspace.", "positive",
    ),
    "migration.import.rolled_back": ActivityDefinition(
        "migration_rolled_back", "workspace", "Imported data removed",
        "Records created by an earlier import were removed while its history was kept.",
    ),
    "billing.portal.created": ActivityDefinition(
        "billing_portal_opened", "workspace", "Billing settings opened",
        "The workspace owner opened the secure billing management page.",
    ),
    "billing.state.updated": ActivityDefinition(
        "billing_state_updated", "workspace", "Billing status changed",
        "The saved subscription status changed after a verified billing update.",
    ),
    "billing.subscription.rotated": ActivityDefinition(
        "billing_subscription_replaced", "workspace", "Subscription replaced",
        "A completed checkout replaced a previous finished subscription.",
    ),
    "platform.org.plan.updated": ActivityDefinition(
        "workspace_plan_updated", "workspace", "Workspace plan changed",
        "The saved workspace plan was changed by authorized support.",
    ),
    "platform.org.status.updated": ActivityDefinition(
        "workspace_status_updated", "workspace", "Workspace status changed",
        "The workspace status was changed by authorized support.",
    ),
    "governance.organization_closure.requested": ActivityDefinition(
        "workspace_closure_requested", "workspace", "Workspace closure requested",
        "The workspace owner started the recoverable closure process.", "attention",
    ),
    "governance.organization_closure.cancelled": ActivityDefinition(
        "workspace_closure_cancelled", "workspace", "Workspace closure canceled",
        "The workspace owner stopped the closure process during its recovery period.", "positive",
    ),
    "reputation.review_reply.publish_requested": ActivityDefinition(
        "review_reply_requested", "reviews", "Review reply requested",
        "A reviewed customer-reply action was requested.",
    ),
    "reputation.review_reply.publish_confirmed": ActivityDefinition(
        "review_reply_confirmed", "reviews", "Review reply confirmed",
        "The connected profile confirmed the approved reply action.", "positive",
    ),
    "reputation.review_reply.publish_blocked": ActivityDefinition(
        "review_reply_blocked", "reviews", "Review reply blocked",
        "A reply action was stopped before publishing because a required check did not pass.", "attention",
    ),
}


class EnterpriseActivityError(ValueError):
    def __init__(self, message: str, *, reason_code: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.status_code = status_code


def _cursor_key() -> bytes:
    secret = (get_settings().jwt_secret + ":enterprise-activity-v1").encode("utf-8")
    return hashlib.sha256(secret).digest()


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _encode_cursor(row: AuditLog, *, category: str | None) -> str:
    packed = json.dumps(
        [row.tenant_id, category, _utc(row.created_at).isoformat(), row.id],
        separators=(",", ":"),
    ).encode("utf-8")
    nonce = os.urandom(12)
    ciphertext = AESGCM(_cursor_key()).encrypt(
        nonce, packed, b"enterprise-activity-cursor-v1"
    )
    return base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii").rstrip("=")


def _decode_cursor(
    cursor: str, *, organization_id: str, category: str | None
) -> tuple[datetime, str]:
    try:
        padding = "=" * (-len(cursor) % 4)
        encrypted = base64.urlsafe_b64decode(cursor + padding)
        if len(encrypted) <= 28:
            raise ValueError("length")
        decoded = json.loads(
            AESGCM(_cursor_key()).decrypt(
                encrypted[:12],
                encrypted[12:],
                b"enterprise-activity-cursor-v1",
            )
        )
        if not isinstance(decoded, list) or len(decoded) != 4:
            raise ValueError("shape")
        if str(decoded[0]) != organization_id:
            raise ValueError("scope")
        if decoded[1] != category:
            raise ValueError("filter")
        return _utc(datetime.fromisoformat(str(decoded[2]))), str(decoded[3])
    except Exception as exc:  # noqa: BLE001
        raise EnterpriseActivityError(
            "This activity page link is no longer valid. Reload the page to continue.",
            reason_code="organization_activity_cursor_invalid",
        ) from exc


def list_organization_activity(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    requesting_user_id: str,
    category: str | None,
    cursor: str | None,
    limit: int,
) -> dict[str, Any]:
    if tenant_id != organization_id:
        raise EnterpriseActivityError(
            "Organization context does not match this request.",
            reason_code="organization_scope_mismatch",
            status_code=404,
        )
    require_commercial_feature(
        db,
        organization_id=organization_id,
        feature_code=FEATURE_ORGANIZATION_ACTIVITY,
    )
    if category is not None and category not in CATEGORY_LABELS:
        raise EnterpriseActivityError(
            "Choose one of the available activity categories.",
            reason_code="organization_activity_category_invalid",
        )

    event_types = [
        event_type
        for event_type, definition in EVENT_CATALOG.items()
        if category is None or definition.category == category
    ]
    query = db.query(AuditLog).filter(
        AuditLog.tenant_id == organization_id,
        AuditLog.event_type.in_(event_types),
    )
    if cursor:
        created_at, row_id = _decode_cursor(
            cursor, organization_id=organization_id, category=category
        )
        query = query.filter(
            or_(
                AuditLog.created_at < created_at,
                and_(AuditLog.created_at == created_at, AuditLog.id < row_id),
            )
        )
    rows = query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit + 1).all()
    has_more = len(rows) > limit
    visible_rows = rows[:limit]

    actor_ids = {row.actor_user_id for row in visible_rows if row.actor_user_id}
    actors = {
        user.id: user
        for user in db.query(User)
        .filter(User.tenant_id == organization_id, User.id.in_(actor_ids))
        .all()
    } if actor_ids else {}

    items: list[dict[str, Any]] = []
    for row in visible_rows:
        definition = EVENT_CATALOG[row.event_type]
        actor = actors.get(row.actor_user_id or "")
        if row.actor_user_id == requesting_user_id:
            actor_label, actor_type = "You", "you"
        elif actor is not None and actor.is_platform_user:
            actor_label, actor_type = "InsightOS support", "support"
        elif actor is not None:
            actor_label, actor_type = actor.email, "team_member"
        else:
            actor_label, actor_type = "InsightOS", "system"
        items.append(
            {
                "kind": definition.kind,
                "category": definition.category,
                "category_label": CATEGORY_LABELS[definition.category],
                "title": definition.title,
                "summary": definition.summary,
                "tone": definition.tone,
                "actor": {"label": actor_label, "type": actor_type},
                "occurred_at": _utc(row.created_at).isoformat(),
            }
        )

    return {
        "items": items,
        "count": len(items),
        "has_more": has_more,
        "next_cursor": (
            _encode_cursor(visible_rows[-1], category=category)
            if has_more and visible_rows
            else None
        ),
        "selected_category": category,
        "categories": [
            {"id": category_id, "label": label}
            for category_id, label in CATEGORY_LABELS.items()
        ],
        "truth": {
            "summary": "This view shows important saved workspace actions, not every background check.",
            "raw_payloads_exposed": False,
            "internal_event_names_exposed": False,
            "internal_identifiers_exposed": False,
            "provider_diagnostics_included": False,
            "unknown_events_excluded": True,
        },
    }
