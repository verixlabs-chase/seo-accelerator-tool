from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy.orm import Session

from app.models.business_location import BusinessLocation
from app.models.business_service import BusinessService
from app.models.business_service_area import BusinessServiceArea
from app.models.campaign import Campaign
from app.models.data_connection import DataConnection
from app.models.data_governance import (
    DataExportRequest,
    OrganizationClosureRequest,
    OrganizationDeletionTombstone,
    ProviderDisconnectRequest,
)
from app.models.intelligence import StrategyRecommendation
from app.models.migration_import import MigrationImportBatch, MigrationImportRecord
from app.models.organization import Organization
from app.models.organization_membership import OrganizationMembership
from app.models.rank import CampaignKeyword, KeywordCluster, Ranking, RankingSnapshot
from app.models.reporting import MonthlyReport, ReportArtifact, ReportRecipient
from app.models.user import User
from app.services.audit_service import write_audit_log


EXPORT_SCHEMA_VERSION = "gov1.customer-export.v1"
EXPORT_TTL = timedelta(days=7)
MAX_EXPORT_BYTES = 15 * 1024 * 1024


class DataGovernanceError(ValueError):
    def __init__(self, message: str, *, reason_code: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


def create_data_export(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    actor_user_id: str,
    client_request_id: str,
) -> dict[str, Any]:
    existing = (
        db.query(DataExportRequest)
        .filter(
            DataExportRequest.organization_id == organization_id,
            DataExportRequest.tenant_id == tenant_id,
            DataExportRequest.client_request_id == client_request_id,
        )
        .first()
    )
    if existing is not None:
        return serialize_data_export(existing)

    now = datetime.now(UTC)
    row = DataExportRequest(
        tenant_id=tenant_id,
        organization_id=organization_id,
        client_request_id=client_request_id,
        requested_by_user_id=actor_user_id,
        status="processing",
        format="json",
        schema_version=EXPORT_SCHEMA_VERSION,
        record_counts={},
        requested_at=now,
        expires_at=now + EXPORT_TTL,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()

    payload = _build_export_payload(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        export_id=row.id,
        generated_at=now,
    )
    content = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=_json_default,
    )
    encoded = content.encode("utf-8")
    if len(encoded) > MAX_EXPORT_BYTES:
        row.status = "failed"
        row.failure_code = "export_too_large"
        row.completed_at = now
        row.updated_at = now
        write_audit_log(
            db,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            event_type="governance.data_export.failed",
            payload={
                "organization_id": organization_id,
                "export_id": row.id,
                "reason_code": row.failure_code,
            },
        )
        db.flush()
        return serialize_data_export(row)

    row.status = "ready"
    row.record_counts = payload["record_counts"]
    row.artifact_content = content
    row.artifact_sha256 = hashlib.sha256(encoded).hexdigest()
    row.artifact_byte_size = len(encoded)
    row.completed_at = now
    row.updated_at = now
    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        event_type="governance.data_export.ready",
        payload={
            "organization_id": organization_id,
            "export_id": row.id,
            "schema_version": row.schema_version,
            "artifact_sha256": row.artifact_sha256,
            "artifact_byte_size": row.artifact_byte_size,
            "record_counts": row.record_counts,
            "expires_at": row.expires_at.isoformat(),
        },
    )
    db.flush()
    return serialize_data_export(row)


def list_data_exports(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
) -> list[dict[str, Any]]:
    rows = (
        db.query(DataExportRequest)
        .filter(
            DataExportRequest.organization_id == organization_id,
            DataExportRequest.tenant_id == tenant_id,
        )
        .order_by(DataExportRequest.created_at.desc(), DataExportRequest.id.desc())
        .limit(25)
        .all()
    )
    return [serialize_data_export(row) for row in rows]


def download_data_export(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    actor_user_id: str,
    export_id: str,
) -> tuple[str, str]:
    row = _export_row(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        export_id=export_id,
        for_update=True,
    )
    expires_at = _as_utc(row.expires_at)
    if datetime.now(UTC) >= expires_at or row.status == "expired":
        raise DataGovernanceError(
            "This export expired. Create a new copy from Settings.",
            reason_code="data_export_expired",
        )
    if row.status != "ready" or not row.artifact_content:
        raise DataGovernanceError(
            "This export is not ready to download.",
            reason_code="data_export_not_ready",
        )
    actual_hash = hashlib.sha256(row.artifact_content.encode("utf-8")).hexdigest()
    if actual_hash != row.artifact_sha256:
        raise DataGovernanceError(
            "This export failed its integrity check. Create a new copy.",
            reason_code="data_export_integrity_failed",
        )
    now = datetime.now(UTC)
    row.downloaded_at = now
    row.updated_at = now
    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        event_type="governance.data_export.downloaded",
        payload={
            "organization_id": organization_id,
            "export_id": row.id,
            "artifact_sha256": row.artifact_sha256,
        },
    )
    filename = f"insightos-account-export-{row.created_at.date().isoformat()}.json"
    db.flush()
    return row.artifact_content, filename


def expire_data_export_artifacts(
    db: Session,
    *,
    now: datetime | None = None,
) -> dict[str, int]:
    cutoff = now or datetime.now(UTC)
    rows = (
        db.query(DataExportRequest)
        .filter(
            DataExportRequest.expires_at <= cutoff,
            DataExportRequest.artifact_content.is_not(None),
        )
        .all()
    )
    for row in rows:
        row.artifact_content = None
        row.status = "expired"
        row.updated_at = cutoff
    db.flush()
    return {"artifacts_expired": len(rows)}


def serialize_data_export(row: DataExportRequest) -> dict[str, Any]:
    return {
        "id": row.id,
        "status": row.status,
        "format": row.format,
        "schema_version": row.schema_version,
        "record_counts": row.record_counts or {},
        "artifact_sha256": row.artifact_sha256,
        "artifact_byte_size": row.artifact_byte_size,
        "failure_code": row.failure_code,
        "requested_at": row.requested_at.isoformat(),
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        "downloaded_at": row.downloaded_at.isoformat() if row.downloaded_at else None,
        "expires_at": row.expires_at.isoformat(),
        "download_available": row.status == "ready" and bool(row.artifact_content),
    }


def _build_export_payload(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    export_id: str,
    generated_at: datetime,
) -> dict[str, Any]:
    organization = db.query(Organization).filter(Organization.id == organization_id).one()
    campaigns = (
        db.query(Campaign)
        .filter(Campaign.organization_id == organization_id, Campaign.tenant_id == tenant_id)
        .order_by(Campaign.created_at.asc(), Campaign.id.asc())
        .all()
    )
    campaign_ids = [row.id for row in campaigns]

    sections: dict[str, list[dict[str, Any]]] = {
        "organization": [
            _fields(organization, "id", "name", "plan_type", "status", "created_at", "updated_at")
        ],
        "members": [
            {
                "membership_id": membership.id,
                "user_id": user.id,
                "email": user.email,
                "role": membership.role,
                "status": membership.status,
                "created_at": membership.created_at,
            }
            for membership, user in (
                db.query(OrganizationMembership, User)
                .join(User, User.id == OrganizationMembership.user_id)
                .filter(OrganizationMembership.organization_id == organization_id)
                .order_by(OrganizationMembership.created_at.asc())
                .all()
            )
        ],
        "locations": _query_fields(
            db.query(BusinessLocation)
            .filter(BusinessLocation.organization_id == organization_id)
            .order_by(BusinessLocation.created_at.asc(), BusinessLocation.id.asc()),
            "id", "sub_account_id", "name", "domain", "city", "region", "country_code",
            "address_line1", "postal_code", "latitude", "longitude", "status", "created_at",
            "updated_at",
        ),
        "campaigns": [
            _fields(
                row, "id", "business_location_id", "sub_account_id", "name", "domain",
                "setup_state", "manual_automation_lock", "created_at",
            )
            for row in campaigns
        ],
        "services": _query_fields(
            db.query(BusinessService)
            .filter(BusinessService.organization_id == organization_id)
            .order_by(BusinessService.created_at.asc(), BusinessService.id.asc()),
            "id", "business_location_id", "scope_type", "name", "aliases", "canonical_category",
            "status", "source", "confidence", "evidence", "reviewed_at", "created_at", "updated_at",
        ),
        "service_areas": _query_fields(
            db.query(BusinessServiceArea)
            .filter(BusinessServiceArea.organization_id == organization_id)
            .order_by(BusinessServiceArea.created_at.asc(), BusinessServiceArea.id.asc()),
            "id", "business_location_id", "area_type", "name", "region", "country_code",
            "radius_miles", "travel_minutes", "center_latitude", "center_longitude",
            "boundary_points", "relationship", "status", "source", "confidence", "evidence",
            "reviewed_at", "created_at", "updated_at",
        ),
        "data_connections": _query_fields(
            db.query(DataConnection)
            .filter(DataConnection.organization_id == organization_id)
            .order_by(DataConnection.created_at.asc(), DataConnection.id.asc()),
            "id", "business_location_id", "campaign_id", "provider_name", "external_resource_id",
            "external_resource_name", "resource_scope", "status", "last_success_at", "created_at",
            "updated_at",
        ),
        "keyword_groups": _scoped_fields(
            db, KeywordCluster, campaign_ids, "id", "campaign_id", "name", "created_at"
        ),
        "tracked_searches": _scoped_fields(
            db, CampaignKeyword, campaign_ids, "id", "campaign_id", "cluster_id", "keyword",
            "location_code", "created_at",
        ),
        "current_rankings": _scoped_fields(
            db, Ranking, campaign_ids, "id", "campaign_id", "keyword_id", "current_position",
            "previous_position", "delta", "confidence", "updated_at",
        ),
        "ranking_history": _scoped_fields(
            db, RankingSnapshot, campaign_ids, "id", "campaign_id", "keyword_id", "position",
            "confidence", "captured_at", "source_type", "source_system", "source_record_id",
            "import_batch_id",
        ),
        "recommendations": _scoped_fields(
            db, StrategyRecommendation, campaign_ids, "id", "campaign_id", "recommendation_type",
            "rationale", "confidence_score", "evidence_json", "risk_tier", "status",
            "engine_version", "created_at",
        ),
        "reports": _scoped_fields(
            db, MonthlyReport, campaign_ids, "id", "campaign_id", "month_number", "report_status",
            "summary_json", "generated_at",
        ),
        "report_files": _scoped_fields(
            db, ReportArtifact, campaign_ids, "id", "campaign_id", "report_id", "artifact_type",
            "content_type", "byte_size", "checksum_sha256", "durable", "ready", "created_at",
        ),
        "report_recipients": _query_fields(
            db.query(ReportRecipient)
            .filter(ReportRecipient.organization_id == organization_id)
            .order_by(ReportRecipient.created_at.asc(), ReportRecipient.id.asc()),
            "id", "campaign_id", "email", "display_name", "recipient_role", "enabled",
            "source_type", "source_system", "source_record_id", "import_batch_id", "created_at",
            "updated_at",
        ),
        "import_batches": _query_fields(
            db.query(MigrationImportBatch)
            .filter(MigrationImportBatch.organization_id == organization_id)
            .order_by(MigrationImportBatch.created_at.asc(), MigrationImportBatch.id.asc()),
            "id", "source_system", "source_filename", "source_sha256", "review_hash", "status",
            "summary", "applied_at", "rolled_back_at", "created_at",
        ),
        "import_records": _query_fields(
            db.query(MigrationImportRecord)
            .filter(MigrationImportRecord.organization_id == organization_id)
            .order_by(MigrationImportRecord.created_at.asc(), MigrationImportRecord.id.asc()),
            "id", "batch_id", "row_number", "record_type", "status", "source_values", "result",
            "created_entities", "created_at",
        ),
        "provider_disconnect_history": _query_fields(
            db.query(ProviderDisconnectRequest)
            .filter(ProviderDisconnectRequest.organization_id == organization_id)
            .order_by(
                ProviderDisconnectRequest.created_at.asc(),
                ProviderDisconnectRequest.id.asc(),
            ),
            "id", "provider_name", "status", "credential_deleted",
            "external_revocation_status", "external_revocation_code",
            "connections_disconnected", "queued_jobs_cancelled",
            "preserved_record_counts", "requested_at", "completed_at", "created_at",
        ),
        "workspace_closure_history": _query_fields(
            db.query(OrganizationClosureRequest)
            .filter(OrganizationClosureRequest.organization_id == organization_id)
            .order_by(
                OrganizationClosureRequest.created_at.asc(),
                OrganizationClosureRequest.id.asc(),
            ),
            "id", "status", "hold_status", "action_counts", "requested_at",
            "recovery_until", "cancelled_at", "closed_at", "deletion_ready_at", "created_at",
        ),
        "workspace_deletion_status": _query_fields(
            db.query(OrganizationDeletionTombstone)
            .filter(OrganizationDeletionTombstone.organization_id == organization_id)
            .order_by(OrganizationDeletionTombstone.created_at.asc()),
            "id", "state", "primary_store_status", "backup_reapply_required",
            "delete_not_before", "primary_store_deleted_at", "verification_completed_at",
            "created_at",
        ),
    }
    return {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "export_id": export_id,
        "generated_at": generated_at.isoformat(),
        "organization_id": organization_id,
        "record_counts": {key: len(value) for key, value in sections.items()},
        "included_data": list(sections.keys()),
        "excluded_data": [
            "password hashes",
            "session tokens and cookies",
            "OAuth and provider credentials",
            "billing provider identifiers",
            "internal provider secrets",
            "report file binary contents",
            "security and legal-hold evidence",
        ],
        "data": sections,
    }


def _scoped_fields(
    db: Session,
    model: Any,
    campaign_ids: list[str],
    *field_names: str,
) -> list[dict[str, Any]]:
    if not campaign_ids:
        return []
    query = db.query(model).filter(model.campaign_id.in_(campaign_ids))
    created_at = getattr(model, "created_at", None)
    if created_at is not None:
        query = query.order_by(created_at.asc(), model.id.asc())
    else:
        query = query.order_by(model.id.asc())
    return [_fields(row, *field_names) for row in query.all()]


def _query_fields(query: Any, *field_names: str) -> list[dict[str, Any]]:
    return [_fields(row, *field_names) for row in query.all()]


def _fields(row: Any, *field_names: str) -> dict[str, Any]:
    return {name: _json_value(getattr(row, name)) for name in field_names}


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Enum):
        return value.value
    return value


def _json_default(value: Any) -> Any:
    converted = _json_value(value)
    if converted is value:
        raise TypeError(f"Unsupported export value: {type(value).__name__}")
    return converted


def _export_row(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    export_id: str,
    for_update: bool = False,
) -> DataExportRequest:
    query = db.query(DataExportRequest).filter(
        DataExportRequest.id == export_id,
        DataExportRequest.tenant_id == tenant_id,
        DataExportRequest.organization_id == organization_id,
    )
    if for_update:
        query = query.with_for_update()
    row = query.first()
    if row is None:
        raise DataGovernanceError(
            "This account export could not be found.",
            reason_code="data_export_not_found",
        )
    return row


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
