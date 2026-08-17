from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

import app.models  # noqa: F401  # Register every mapped table for rollback dependency checks.
from app.db.base import Base
from app.models.authority import DirectoryListing, DirectoryListingObservation
from app.models.business_location import BusinessLocation
from app.models.campaign import Campaign
from app.models.competitor import Competitor
from app.models.migration_import import MigrationImportBatch, MigrationImportRecord
from app.models.organization import Organization
from app.models.portfolio import Portfolio
from app.models.rank import CampaignKeyword, KeywordCluster, RankingSnapshot
from app.models.reporting import ReportRecipient
from app.services.audit_service import write_audit_log
from app.services.business_location_service import (
    BusinessLocationConflictError,
    create_business_location_with_portfolio,
)
from app.services.location_allowance_service import (
    ActiveLocationAllowanceError,
    assert_active_location_capacity,
)
from app.services.listing_inventory_service import compare_listing_fields


MAX_IMPORT_ROWS = 2_500
MAX_CELL_LENGTH = 1_000
RECORD_TYPES = {
    "location",
    "keyword",
    "competitor",
    "ranking",
    "listing",
    "report_recipient",
}
CANONICAL_FIELDS = (
    "record_type",
    "location_name",
    "website",
    "city",
    "region",
    "country_code",
    "postal_code",
    "phrase",
    "keyword_group",
    "competitor_domain",
    "position",
    "captured_at",
    "source_record_id",
    "directory_name",
    "listing_url",
    "listing_status",
    "listing_business_name",
    "listing_address",
    "listing_city",
    "listing_region",
    "listing_postal_code",
    "listing_phone",
    "listing_website",
    "primary_category",
    "directory_importance",
    "recipient_email",
    "recipient_name",
    "recipient_role",
)
FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "record_type": ("record_type", "type", "row_type"),
    "location_name": ("location_name", "location", "business_name", "campaign"),
    "website": ("website", "domain", "site", "url"),
    "city": ("city", "locality"),
    "region": ("region", "state", "province"),
    "country_code": ("country_code", "country"),
    "postal_code": ("postal_code", "zip", "zip_code", "postcode"),
    "phrase": ("phrase", "keyword", "search_term"),
    "keyword_group": ("keyword_group", "group", "cluster", "tag"),
    "competitor_domain": ("competitor_domain", "competitor", "competitor_website"),
    "position": ("position", "rank", "ranking", "current_position"),
    "captured_at": ("captured_at", "date", "snapshot_date", "tracked_at", "last_updated"),
    "source_record_id": ("source_record_id", "original_id", "record_id"),
    "directory_name": ("directory_name", "directory", "listing_source", "citation_source"),
    "listing_url": ("listing_url", "citation_url", "profile_url", "directory_url"),
    "listing_status": ("listing_status", "citation_status", "source_status"),
    "listing_business_name": (
        "listing_business_name",
        "listed_business_name",
        "name_on_listing",
    ),
    "listing_address": ("listing_address", "listed_address", "address_on_listing"),
    "listing_city": ("listing_city", "listed_city"),
    "listing_region": ("listing_region", "listed_region", "listing_state"),
    "listing_postal_code": ("listing_postal_code", "listed_postal_code", "listing_zip"),
    "listing_phone": ("listing_phone", "listed_phone", "phone_on_listing"),
    "listing_website": ("listing_website", "listed_website", "website_on_listing"),
    "primary_category": ("primary_category", "listing_category", "category_on_listing"),
    "directory_importance": ("directory_importance", "listing_importance", "importance"),
    "recipient_email": ("recipient_email", "report_email", "delivery_email"),
    "recipient_name": ("recipient_name", "report_recipient_name", "delivery_name"),
    "recipient_role": ("recipient_role", "report_recipient_role", "delivery_role"),
}

SOURCE_FIELD_ALIASES: dict[str, dict[str, tuple[str, ...]]] = {
    "semrush": {
        "location_name": ("project", "project_name"),
        "website": ("root_domain", "target_url"),
        "keyword_group": ("tag", "tags"),
        "competitor_domain": ("competitor_url",),
        "captured_at": ("last_update", "last_updated"),
    },
    "brightlocal": {
        "location_name": ("business", "business_location"),
        "website": ("website_url", "business_website"),
        "city": ("town",),
        "phrase": ("search_query",),
        "captured_at": ("last_checked", "date_updated"),
        "directory_name": ("citation_name", "publisher"),
        "listing_url": ("citation_link", "live_url"),
        "listing_status": ("citation_state",),
    },
}


class MigrationImportError(ValueError):
    def __init__(self, message: str, *, reason_code: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


def dry_run_migration_csv(
    db: Session,
    *,
    organization_id: str,
    tenant_id: str,
    source_system: str,
    csv_text: str,
    max_rows: int = MAX_IMPORT_ROWS,
) -> dict[str, Any]:
    reader, field_mapping, ignored_headers, adapter_name = _reader(
        csv_text,
        source_system=source_system,
    )
    raw_rows: list[dict[str, str]] = []
    ignored_column_counts = {header: 0 for header, _reason in ignored_headers}
    try:
        for raw_row in reader:
            if len(raw_rows) >= max_rows:
                raise MigrationImportError(
                    f"Review no more than {max_rows:,} rows at one time.",
                    reason_code="migration_row_limit_exceeded",
                )
            for header in ignored_column_counts:
                if str(raw_row.get(header) or "").strip():
                    ignored_column_counts[header] += 1
            raw_rows.append(_canonical_row(raw_row, field_mapping))
    except csv.Error as exc:
        raise MigrationImportError(
            "The file could not be read as a CSV.",
            reason_code="migration_csv_invalid",
        ) from exc

    if not raw_rows:
        raise MigrationImportError(
            "The file has headings but no data rows.",
            reason_code="migration_csv_empty",
        )

    existing_locations = (
        db.query(BusinessLocation)
        .filter(BusinessLocation.organization_id == organization_id)
        .order_by(BusinessLocation.created_at.asc(), BusinessLocation.id.asc())
        .all()
    )
    locations_by_name: dict[str, list[BusinessLocation]] = defaultdict(list)
    locations_by_domain: dict[str, list[BusinessLocation]] = defaultdict(list)
    for location in existing_locations:
        locations_by_name[_text_key(location.name)].append(location)
        domain = _domain(location.domain)
        if domain:
            locations_by_domain[domain].append(location)

    campaigns = (
        db.query(Campaign)
        .filter(
            Campaign.organization_id == organization_id,
            Campaign.tenant_id == tenant_id,
            Campaign.business_location_id.is_not(None),
        )
        .all()
    )
    campaign_by_location = {
        str(row.business_location_id): row for row in campaigns if row.business_location_id
    }
    campaign_ids = [row.id for row in campaigns]
    existing_keywords: dict[str, set[str]] = defaultdict(set)
    existing_competitors: dict[str, set[str]] = defaultdict(set)
    existing_rankings: dict[tuple[str, str, str], set[int]] = defaultdict(set)
    existing_listing_evidence: set[tuple[str, str, str, str]] = set()
    existing_recipients: dict[str, set[str]] = defaultdict(set)
    if campaign_ids:
        for row in (
            db.query(CampaignKeyword)
            .filter(
                CampaignKeyword.tenant_id == tenant_id,
                CampaignKeyword.campaign_id.in_(campaign_ids),
            )
            .all()
        ):
            existing_keywords[row.campaign_id].add(_text_key(row.keyword))
        for row in (
            db.query(Competitor)
            .filter(
                Competitor.tenant_id == tenant_id,
                Competitor.campaign_id.in_(campaign_ids),
            )
            .all()
        ):
            domain = _domain(row.domain)
            if domain:
                existing_competitors[row.campaign_id].add(domain)
        for snapshot, keyword in (
            db.query(RankingSnapshot, CampaignKeyword)
            .join(CampaignKeyword, CampaignKeyword.id == RankingSnapshot.keyword_id)
            .filter(
                RankingSnapshot.tenant_id == tenant_id,
                RankingSnapshot.campaign_id.in_(campaign_ids),
            )
            .all()
        ):
            captured = _as_utc(snapshot.captured_at)
            existing_rankings[
                (snapshot.campaign_id, _text_key(keyword.keyword), captured.isoformat())
            ].add(int(snapshot.position))
        for listing in (
            db.query(DirectoryListing)
            .filter(
                DirectoryListing.tenant_id == tenant_id,
                DirectoryListing.campaign_id.in_(campaign_ids),
                DirectoryListing.source_type == "imported",
            )
            .all()
        ):
            existing_listing_evidence.add(
                _listing_evidence_key(
                    location_id=listing.business_location_id,
                    directory_name=listing.source_name,
                    captured_at=_as_utc(listing.last_seen_at),
                    source_record_id=listing.source_record_id,
                    listing_url=listing.listing_url,
                )
            )
        for recipient in (
            db.query(ReportRecipient)
            .filter(
                ReportRecipient.tenant_id == tenant_id,
                ReportRecipient.campaign_id.in_(campaign_ids),
            )
            .all()
        ):
            existing_recipients[recipient.campaign_id].add(recipient.email.strip().lower())

    file_locations: dict[str, list[dict[str, Any]]] = defaultdict(list)
    file_keywords: dict[tuple[str, str], list[int]] = defaultdict(list)
    for index, row in enumerate(raw_rows, start=2):
        if _record_type(row.get("record_type")) == "location" and row.get("location_name"):
            file_locations[_text_key(row["location_name"])].append(
                {"row_number": index, "domain": _domain(row.get("website"))}
            )
        if _record_type(row.get("record_type")) == "keyword" and row.get("location_name"):
            file_keywords[
                (_text_key(row["location_name"]), _text_key(row.get("phrase")))
            ].append(index)

    seen: set[tuple[str, ...]] = set()
    results: list[dict[str, Any]] = []
    for row_number, row in enumerate(raw_rows, start=2):
        results.append(
            _review_row(
                row_number=row_number,
                row=row,
                seen=seen,
                file_locations=file_locations,
                file_keywords=file_keywords,
                locations_by_name=locations_by_name,
                locations_by_domain=locations_by_domain,
                campaign_by_location=campaign_by_location,
                existing_keywords=existing_keywords,
                existing_competitors=existing_competitors,
                existing_rankings=existing_rankings,
                existing_listing_evidence=existing_listing_evidence,
                existing_recipients=existing_recipients,
            )
        )

    statuses = Counter(str(row["status"]) for row in results)
    types = Counter(str(row["record_type"]) for row in results if row["record_type"] in RECORD_TYPES)
    result = {
        "mode": "dry_run",
        "source_system": source_system,
        "adapter": adapter_name,
        "source_sha256": _source_hash(csv_text),
        "writes_performed": 0,
        "field_mapping": field_mapping,
        "ignored_columns": [
            {
                "column": header,
                "populated_rows": ignored_column_counts[header],
                "reason": reason,
            }
            for header, reason in ignored_headers
        ],
        "summary": {
            "total_rows": len(results),
            "ready": statuses["ready"],
            "already_saved": statuses["already_saved"],
            "duplicates_in_file": statuses["duplicate"],
            "needs_attention": statuses["needs_attention"],
            "locations": types["location"],
            "keywords": types["keyword"],
            "competitors": types["competitor"],
            "ranking_history": types["ranking"],
            "listing_history": types["listing"],
            "report_recipients": types["report_recipient"],
        },
        "rows": results,
        "next_step": (
            "Fix the rows marked Needs attention, then review the ready rows before importing. "
            "Nothing has been changed yet."
        ),
    }
    result["review_hash"] = _review_hash(result)
    return result


def apply_migration_csv(
    db: Session,
    *,
    organization_id: str,
    tenant_id: str,
    actor_user_id: str,
    source_system: str,
    source_filename: str | None,
    csv_text: str,
    review_hash: str,
    client_request_id: str,
    confirmed: bool,
    max_rows: int = MAX_IMPORT_ROWS,
) -> dict[str, Any]:
    if not confirmed:
        raise MigrationImportError(
            "Confirm that you reviewed the rows before importing them.",
            reason_code="migration_confirmation_required",
        )

    source_sha256 = _source_hash(csv_text)
    db.query(Organization).filter(Organization.id == organization_id).with_for_update().one()
    existing_batch = (
        db.query(MigrationImportBatch)
        .filter(
            MigrationImportBatch.organization_id == organization_id,
            MigrationImportBatch.client_request_id == client_request_id,
        )
        .first()
    )
    if existing_batch is not None:
        if (
            existing_batch.source_sha256 != source_sha256
            or existing_batch.review_hash != review_hash
        ):
            raise MigrationImportError(
                "This import request was already used for a different reviewed file.",
                reason_code="migration_idempotency_conflict",
            )
        return serialize_migration_batch(db, existing_batch, include_records=True)

    review = dry_run_migration_csv(
        db,
        organization_id=organization_id,
        tenant_id=tenant_id,
        source_system=source_system,
        csv_text=csv_text,
        max_rows=max_rows,
    )
    if review["review_hash"] != review_hash:
        raise MigrationImportError(
            "The file or saved setup changed after review. Review the file again before importing.",
            reason_code="migration_review_changed",
        )
    if review["summary"]["needs_attention"]:
        raise MigrationImportError(
            "Fix every row marked Needs attention before importing.",
            reason_code="migration_rows_need_attention",
        )
    if not review["summary"]["ready"]:
        raise MigrationImportError(
            "There are no new rows to import.",
            reason_code="migration_nothing_to_import",
        )

    ready_location_count = sum(
        1
        for reviewed_row in review["rows"]
        if reviewed_row["status"] == "ready" and reviewed_row["record_type"] == "location"
    )
    if ready_location_count:
        try:
            assert_active_location_capacity(
                db,
                organization_id=organization_id,
                requested_delta=ready_location_count,
            )
        except ActiveLocationAllowanceError as exc:
            raise MigrationImportError(
                str(exc),
                reason_code=exc.reason_code,
            ) from exc

    now = datetime.now(UTC)
    batch = MigrationImportBatch(
        tenant_id=tenant_id,
        organization_id=organization_id,
        source_system=source_system,
        source_filename=_safe_filename(source_filename),
        source_sha256=source_sha256,
        review_hash=review_hash,
        client_request_id=client_request_id,
        status="applied",
        summary={},
        created_entities=[],
        applied_by=actor_user_id,
        applied_at=now,
        created_at=now,
    )
    db.add(batch)
    db.flush()

    records: dict[int, MigrationImportRecord] = {}
    for reviewed_row in review["rows"]:
        row_status = "pending" if reviewed_row["status"] == "ready" else "skipped"
        record = MigrationImportRecord(
            batch_id=batch.id,
            tenant_id=tenant_id,
            organization_id=organization_id,
            row_number=int(reviewed_row["row_number"]),
            record_type=str(reviewed_row["record_type"]),
            status=row_status,
            source_values=dict(reviewed_row["values"]),
            result={
                "review_status": reviewed_row["status"],
                "detail": reviewed_row["detail"],
                "issues": reviewed_row["issues"],
                "matched_location_id": reviewed_row["matched_location_id"],
                "matched_location_name": reviewed_row["matched_location_name"],
            },
            created_entities=[],
            created_at=now,
        )
        db.add(record)
        records[int(reviewed_row["row_number"])] = record

    created_entities: list[dict[str, str]] = []
    new_locations: dict[str, BusinessLocation] = {}
    campaign_cache: dict[str, Campaign] = {}
    cluster_cache: dict[tuple[str, str], KeywordCluster] = {}
    keyword_cache: dict[tuple[str, str], CampaignKeyword] = {}

    for reviewed_row in review["rows"]:
        if reviewed_row["status"] != "ready" or reviewed_row["record_type"] != "location":
            continue
        values = reviewed_row["values"]
        try:
            payload = create_business_location_with_portfolio(
                db,
                organization_id=organization_id,
                name=values["location_name"],
                domain=_domain(values.get("website")) or None,
                primary_city=values.get("city") or None,
                city=values.get("city") or None,
                region=values.get("region") or None,
                country_code=(values.get("country_code") or "US")[:2].upper(),
                postal_code=values.get("postal_code") or None,
            )
        except BusinessLocationConflictError as exc:
            raise MigrationImportError(
                "A location changed while the import was starting. Review the file again.",
                reason_code="migration_location_changed",
            ) from exc
        db.flush()
        location = db.get(BusinessLocation, str(payload["id"]))
        if location is None:
            raise MigrationImportError(
                "The new location could not be verified.",
                reason_code="migration_location_create_failed",
            )
        portfolio = _portfolio_for_location(db, organization_id, location.id)
        if portfolio is None:
            raise MigrationImportError(
                "The new location workspace could not be verified.",
                reason_code="migration_location_portfolio_missing",
            )
        location_entities = [
            _entity("business_location", location.id),
            _entity("portfolio", portfolio.id),
        ]
        campaign, campaign_created = _ensure_campaign(
            db,
            organization_id=organization_id,
            tenant_id=tenant_id,
            location=location,
        )
        campaign_cache[location.id] = campaign
        if campaign_created:
            location_entities.append(_entity("campaign", campaign.id))
        new_locations[_text_key(location.name)] = location
        _mark_record_applied(records[int(reviewed_row["row_number"])], location_entities)
        created_entities.extend(location_entities)

    for reviewed_row in review["rows"]:
        if (
            reviewed_row["status"] != "ready"
            or reviewed_row["record_type"] not in {"keyword", "competitor"}
        ):
            continue
        values = reviewed_row["values"]
        location = _location_for_reviewed_row(
            db,
            organization_id=organization_id,
            reviewed_row=reviewed_row,
            new_locations=new_locations,
        )
        if location is None:
            raise MigrationImportError(
                "A reviewed location could not be found while applying the import.",
                reason_code="migration_location_changed",
            )
        campaign = campaign_cache.get(location.id)
        campaign_created = False
        if campaign is None:
            campaign, campaign_created = _ensure_campaign(
                db,
                organization_id=organization_id,
                tenant_id=tenant_id,
                location=location,
            )
            campaign_cache[location.id] = campaign
        row_entities: list[dict[str, str]] = []
        if campaign_created:
            row_entities.append(_entity("campaign", campaign.id))

        if reviewed_row["record_type"] == "keyword":
            group_name = (values.get("keyword_group") or "Imported searches")[:120]
            cluster_key = (campaign.id, _text_key(group_name))
            cluster = cluster_cache.get(cluster_key)
            cluster_created = False
            if cluster is None:
                cluster = (
                    db.query(KeywordCluster)
                    .filter(
                        KeywordCluster.tenant_id == tenant_id,
                        KeywordCluster.campaign_id == campaign.id,
                    )
                    .all()
                )
                cluster = next(
                    (item for item in cluster if _text_key(item.name) == _text_key(group_name)),
                    None,
                )
                if cluster is None:
                    cluster = KeywordCluster(
                        tenant_id=tenant_id,
                        campaign_id=campaign.id,
                        name=group_name,
                    )
                    db.add(cluster)
                    db.flush()
                    cluster_created = True
                cluster_cache[cluster_key] = cluster
            if cluster_created:
                row_entities.append(_entity("keyword_cluster", cluster.id))
            keyword = CampaignKeyword(
                tenant_id=tenant_id,
                campaign_id=campaign.id,
                cluster_id=cluster.id,
                keyword=values["phrase"],
                location_code=(location.provider_location_code or location.country_code or "US")[:64],
            )
            db.add(keyword)
            db.flush()
            row_entities.append(_entity("campaign_keyword", keyword.id))
            keyword_cache[(campaign.id, _text_key(keyword.keyword))] = keyword
        else:
            competitor = Competitor(
                tenant_id=tenant_id,
                campaign_id=campaign.id,
                domain=_domain(values.get("competitor_domain")),
                label=None,
                discovery_source=f"migration_{source_system}"[:40],
                review_status="confirmed",
            )
            db.add(competitor)
            db.flush()
            row_entities.append(_entity("competitor", competitor.id))

        _mark_record_applied(records[int(reviewed_row["row_number"])], row_entities)
        created_entities.extend(row_entities)

    for reviewed_row in review["rows"]:
        if reviewed_row["status"] != "ready" or reviewed_row["record_type"] != "ranking":
            continue
        values = reviewed_row["values"]
        location = _location_for_reviewed_row(
            db,
            organization_id=organization_id,
            reviewed_row=reviewed_row,
            new_locations=new_locations,
        )
        if location is None:
            raise MigrationImportError(
                "A reviewed location could not be found while importing ranking history.",
                reason_code="migration_location_changed",
            )
        campaign = campaign_cache.get(location.id)
        if campaign is None:
            campaign, _created = _ensure_campaign(
                db,
                organization_id=organization_id,
                tenant_id=tenant_id,
                location=location,
            )
            campaign_cache[location.id] = campaign
        keyword_key = (campaign.id, _text_key(values.get("phrase")))
        keyword = keyword_cache.get(keyword_key)
        if keyword is None:
            keyword = next(
                (
                    item
                    for item in db.query(CampaignKeyword)
                    .filter(
                        CampaignKeyword.tenant_id == tenant_id,
                        CampaignKeyword.campaign_id == campaign.id,
                    )
                    .all()
                    if _text_key(item.keyword) == keyword_key[1]
                ),
                None,
            )
        captured_at = _parse_import_datetime(values.get("captured_at"))
        position = _parse_position(values.get("position"))
        if keyword is None or captured_at is None or position is None:
            raise MigrationImportError(
                "The reviewed ranking history no longer matches a tracked search.",
                reason_code="migration_ranking_reference_changed",
            )
        snapshot = RankingSnapshot(
            tenant_id=tenant_id,
            campaign_id=campaign.id,
            keyword_id=keyword.id,
            position=position,
            confidence=0.7,
            captured_at=captured_at,
            month_partition=captured_at.strftime("%Y-%m"),
            source_type="imported",
            source_system=source_system,
            source_record_id=(values.get("source_record_id") or None),
            import_batch_id=batch.id,
        )
        db.add(snapshot)
        db.flush()
        snapshot_entities = [_entity("ranking_snapshot", snapshot.id)]
        _mark_record_applied(records[int(reviewed_row["row_number"])], snapshot_entities)
        created_entities.extend(snapshot_entities)

    for reviewed_row in review["rows"]:
        if reviewed_row["status"] != "ready" or reviewed_row["record_type"] != "listing":
            continue
        values = reviewed_row["values"]
        location = _location_for_reviewed_row(
            db,
            organization_id=organization_id,
            reviewed_row=reviewed_row,
            new_locations=new_locations,
        )
        if location is None:
            raise MigrationImportError(
                "A reviewed location could not be found while importing listing history.",
                reason_code="migration_location_changed",
            )
        campaign = campaign_cache.get(location.id)
        if campaign is None:
            campaign, _created = _ensure_campaign(
                db,
                organization_id=organization_id,
                tenant_id=tenant_id,
                location=location,
            )
            campaign_cache[location.id] = campaign
        captured_at = _parse_import_datetime(values.get("captured_at"))
        claimed_status = _listing_claim_status(values.get("listing_status"))
        if captured_at is None or claimed_status is None:
            raise MigrationImportError(
                "The reviewed listing history is no longer valid.",
                reason_code="migration_listing_reference_changed",
            )
        directory_name = str(values.get("directory_name") or "").strip()[:160]
        listing_url = _safe_public_url(values.get("listing_url")) or None
        observed_fields = {
            key: value
            for key, value in {
                "business_name": values.get("listing_business_name"),
                "address_line1": values.get("listing_address"),
                "city": values.get("listing_city"),
                "region": values.get("listing_region"),
                "postal_code": values.get("listing_postal_code"),
                "country_code": values.get("country_code"),
                "phone": values.get("listing_phone"),
                "website_url": values.get("listing_website"),
                "primary_category": values.get("primary_category"),
                "listing_url": listing_url,
            }.items()
            if value not in (None, "")
        }
        differences, comparable_fields = compare_listing_fields(
            location=location,
            observed_fields=observed_fields,
        )
        confidence = (
            round(max(0.0, (comparable_fields - len(differences)) / comparable_fields), 4)
            if comparable_fields
            else 0.0
        )
        source_identity = str(values.get("source_record_id") or listing_url or "").strip()
        external_seed = "|".join(
            (
                location.id,
                source_system,
                directory_name.casefold(),
                captured_at.isoformat(),
                source_identity.casefold(),
            )
        )
        external_id = hashlib.sha256(external_seed.encode("utf-8")).hexdigest()
        source_key = re.sub(r"[^a-z0-9]+", "-", directory_name.casefold()).strip("-")
        source_key = (source_key or f"imported-{external_id[:12]}")[:100]
        importance = _text_key(values.get("directory_importance")) or "unknown"
        listing = DirectoryListing(
            tenant_id=tenant_id,
            organization_id=organization_id,
            campaign_id=campaign.id,
            business_location_id=location.id,
            source_key=source_key,
            source_name=directory_name,
            provider_name="migration",
            external_id=external_id,
            listing_url=listing_url,
            status="unavailable",
            business_name=observed_fields.get("business_name"),
            address_line1=observed_fields.get("address_line1"),
            city=observed_fields.get("city"),
            region=observed_fields.get("region"),
            postal_code=observed_fields.get("postal_code"),
            country_code=observed_fields.get("country_code"),
            phone=observed_fields.get("phone"),
            website_url=observed_fields.get("website_url"),
            primary_category=observed_fields.get("primary_category"),
            observed_fields=observed_fields,
            field_differences=differences,
            directory_importance=importance,
            confidence=confidence,
            first_seen_at=captured_at,
            last_seen_at=captured_at,
            last_verified_at=None,
            source_type="imported",
            source_system=source_system,
            source_record_id=(values.get("source_record_id") or None),
            source_claimed_status=claimed_status,
            import_batch_id=batch.id,
            created_at=now,
            updated_at=now,
        )
        db.add(listing)
        db.flush()
        evidence_payload = json.dumps(
            {
                "source_type": "imported",
                "claimed_status": claimed_status,
                "observed_fields": observed_fields,
                "field_differences": differences,
                "observed_at": captured_at.isoformat(),
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        observation = DirectoryListingObservation(
            tenant_id=tenant_id,
            organization_id=organization_id,
            campaign_id=campaign.id,
            business_location_id=location.id,
            listing_id=listing.id,
            status="unavailable",
            observed_fields=observed_fields,
            field_differences=differences,
            confidence=confidence,
            evidence_digest=hashlib.sha256(evidence_payload.encode("utf-8")).hexdigest(),
            observed_at=captured_at,
            source_type="imported",
            source_system=source_system,
            source_record_id=(values.get("source_record_id") or None),
            source_claimed_status=claimed_status,
            import_batch_id=batch.id,
        )
        db.add(observation)
        db.flush()
        listing_entities = [
            _entity("directory_listing_observation", observation.id),
            _entity("directory_listing", listing.id),
        ]
        record = records[int(reviewed_row["row_number"])]
        record.result = {
            **record.result,
            "source_qualification": "imported_history_not_freshly_verified",
            "source_claimed_status": claimed_status,
        }
        _mark_record_applied(record, listing_entities)
        created_entities.extend(listing_entities)

    for reviewed_row in review["rows"]:
        if (
            reviewed_row["status"] != "ready"
            or reviewed_row["record_type"] != "report_recipient"
        ):
            continue
        values = reviewed_row["values"]
        location = _location_for_reviewed_row(
            db,
            organization_id=organization_id,
            reviewed_row=reviewed_row,
            new_locations=new_locations,
        )
        if location is None:
            raise MigrationImportError(
                "A reviewed location could not be found while importing report recipients.",
                reason_code="migration_location_changed",
            )
        campaign = campaign_cache.get(location.id)
        if campaign is None:
            campaign, _created = _ensure_campaign(
                db,
                organization_id=organization_id,
                tenant_id=tenant_id,
                location=location,
            )
            campaign_cache[location.id] = campaign
        email = _normalized_email(values.get("recipient_email"))
        role = _recipient_role(values.get("recipient_role"))
        if email is None or role is None:
            raise MigrationImportError(
                "The reviewed report recipient is no longer valid.",
                reason_code="migration_recipient_changed",
            )
        recipient = ReportRecipient(
            tenant_id=tenant_id,
            organization_id=organization_id,
            campaign_id=campaign.id,
            email=email,
            display_name=(str(values.get("recipient_name") or "").strip()[:160] or None),
            recipient_role=role,
            enabled=False,
            source_type="imported",
            source_system=source_system,
            source_record_id=(values.get("source_record_id") or None),
            import_batch_id=batch.id,
            created_at=now,
            updated_at=now,
        )
        db.add(recipient)
        db.flush()
        recipient_entities = [_entity("report_recipient", recipient.id)]
        record = records[int(reviewed_row["row_number"])]
        record.result = {
            **record.result,
            "delivery_state": "disabled_until_owner_review",
        }
        _mark_record_applied(record, recipient_entities)
        created_entities.extend(recipient_entities)

    created_entities = _deduplicate_entities(created_entities)
    counts = Counter(item["entity_type"] for item in created_entities)
    batch.created_entities = created_entities
    batch.summary = {
        **review["summary"],
        "records_applied": sum(1 for row in records.values() if row.status == "applied"),
        "locations_created": counts["business_location"],
        "keywords_created": counts["campaign_keyword"],
        "competitors_created": counts["competitor"],
        "ranking_history_created": counts["ranking_snapshot"],
        "listing_history_created": counts["directory_listing"],
        "report_recipients_created": counts["report_recipient"],
    }
    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        event_type="migration.import.applied",
        payload={
            "batch_id": batch.id,
            "organization_id": organization_id,
            "source_system": source_system,
            "source_sha256": source_sha256,
            "review_hash": review_hash,
            "summary": batch.summary,
        },
    )
    db.flush()
    return serialize_migration_batch(db, batch, include_records=True)


def list_migration_batches(
    db: Session,
    *,
    organization_id: str,
    tenant_id: str,
) -> list[dict[str, Any]]:
    rows = (
        db.query(MigrationImportBatch)
        .filter(
            MigrationImportBatch.organization_id == organization_id,
            MigrationImportBatch.tenant_id == tenant_id,
        )
        .order_by(MigrationImportBatch.created_at.desc(), MigrationImportBatch.id.desc())
        .limit(50)
        .all()
    )
    return [serialize_migration_batch(db, row, include_records=False) for row in rows]


def rollback_migration_batch(
    db: Session,
    *,
    organization_id: str,
    tenant_id: str,
    actor_user_id: str,
    batch_id: str,
    confirmed: bool,
) -> dict[str, Any]:
    if not confirmed:
        raise MigrationImportError(
            "Confirm that you want to remove the records created by this import.",
            reason_code="migration_rollback_confirmation_required",
        )
    batch = (
        db.query(MigrationImportBatch)
        .filter(
            MigrationImportBatch.id == batch_id,
            MigrationImportBatch.organization_id == organization_id,
            MigrationImportBatch.tenant_id == tenant_id,
        )
        .with_for_update()
        .first()
    )
    if batch is None:
        raise MigrationImportError(
            "Import batch not found.",
            reason_code="migration_batch_not_found",
        )
    if batch.status == "rolled_back":
        return serialize_migration_batch(db, batch, include_records=True)
    if batch.status != "applied":
        raise MigrationImportError(
            "Only an applied import can be rolled back.",
            reason_code="migration_batch_not_applied",
        )

    entities = _entities_by_type(batch.created_entities)
    blockers = _rollback_blockers(db, entities)
    if blockers:
        raise MigrationImportError(
            "This import now has newer work attached to it. Remove that work first or keep the import.",
            reason_code="migration_rollback_blocked_by_new_work",
        )

    _delete_created_entities(db, organization_id, tenant_id, entities)
    rolled_back_at = datetime.now(UTC)
    batch.status = "rolled_back"
    batch.rolled_back_by = actor_user_id
    batch.rolled_back_at = rolled_back_at
    (
        db.query(MigrationImportRecord)
        .filter(
            MigrationImportRecord.batch_id == batch.id,
            MigrationImportRecord.status == "applied",
        )
        .update({MigrationImportRecord.status: "rolled_back"}, synchronize_session=False)
    )
    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        event_type="migration.import.rolled_back",
        payload={
            "batch_id": batch.id,
            "organization_id": organization_id,
            "source_sha256": batch.source_sha256,
            "review_hash": batch.review_hash,
            "removed_entities": sum(len(values) for values in entities.values()),
        },
    )
    db.flush()
    return serialize_migration_batch(db, batch, include_records=True)


def serialize_migration_batch(
    db: Session,
    batch: MigrationImportBatch,
    *,
    include_records: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": batch.id,
        "source_system": batch.source_system,
        "source_filename": batch.source_filename,
        "source_sha256": batch.source_sha256,
        "review_hash": batch.review_hash,
        "client_request_id": batch.client_request_id,
        "status": batch.status,
        "summary": batch.summary,
        "created_entities": batch.created_entities,
        "applied_by": batch.applied_by,
        "applied_at": batch.applied_at.isoformat(),
        "rolled_back_by": batch.rolled_back_by,
        "rolled_back_at": batch.rolled_back_at.isoformat() if batch.rolled_back_at else None,
        "created_at": batch.created_at.isoformat(),
        "rollback_available": batch.status == "applied",
    }
    if include_records:
        records = (
            db.query(MigrationImportRecord)
            .filter(MigrationImportRecord.batch_id == batch.id)
            .order_by(MigrationImportRecord.row_number.asc())
            .all()
        )
        payload["records"] = [
            {
                "row_number": row.row_number,
                "record_type": row.record_type,
                "status": row.status,
                "source_values": row.source_values,
                "result": row.result,
                "created_entities": row.created_entities,
            }
            for row in records
        ]
    return payload


def _ensure_campaign(
    db: Session,
    *,
    organization_id: str,
    tenant_id: str,
    location: BusinessLocation,
) -> tuple[Campaign, bool]:
    existing = (
        db.query(Campaign)
        .filter(
            Campaign.organization_id == organization_id,
            Campaign.tenant_id == tenant_id,
            Campaign.business_location_id == location.id,
        )
        .order_by(Campaign.created_at.asc(), Campaign.id.asc())
        .first()
    )
    if existing is not None:
        return existing, False
    portfolio = _portfolio_for_location(db, organization_id, location.id)
    if portfolio is None:
        raise MigrationImportError(
            f"{location.name} does not have a workspace for imported searches.",
            reason_code="migration_location_portfolio_missing",
        )
    if not location.domain:
        raise MigrationImportError(
            f"Add a website to {location.name} before importing searches or competitors.",
            reason_code="migration_location_website_missing",
        )
    campaign = Campaign(
        tenant_id=tenant_id,
        organization_id=organization_id,
        portfolio_id=portfolio.id,
        business_location_id=location.id,
        name=location.name,
        domain=location.domain,
        setup_state="Configured",
        manual_automation_lock=True,
    )
    db.add(campaign)
    db.flush()
    return campaign, True


def _portfolio_for_location(
    db: Session,
    organization_id: str,
    location_id: str,
) -> Portfolio | None:
    return (
        db.query(Portfolio)
        .filter(
            Portfolio.organization_id == organization_id,
            Portfolio.business_location_id == location_id,
        )
        .order_by(Portfolio.created_at.asc(), Portfolio.id.asc())
        .first()
    )


def _location_for_reviewed_row(
    db: Session,
    *,
    organization_id: str,
    reviewed_row: dict[str, Any],
    new_locations: dict[str, BusinessLocation],
) -> BusinessLocation | None:
    matched_location_id = reviewed_row.get("matched_location_id")
    if matched_location_id:
        return (
            db.query(BusinessLocation)
            .filter(
                BusinessLocation.id == matched_location_id,
                BusinessLocation.organization_id == organization_id,
            )
            .first()
        )
    return new_locations.get(_text_key(reviewed_row.get("location_name")))


def _mark_record_applied(
    record: MigrationImportRecord,
    entities: list[dict[str, str]],
) -> None:
    record.status = "applied"
    record.created_entities = list(entities)


def _entity(entity_type: str, entity_id: str) -> dict[str, str]:
    return {"entity_type": entity_type, "entity_id": entity_id}


def _deduplicate_entities(entities: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, str]] = []
    for entity in entities:
        key = (entity["entity_type"], entity["entity_id"])
        if key not in seen:
            seen.add(key)
            result.append(entity)
    return result


def _entities_by_type(entities: list[dict[str, Any]]) -> dict[str, set[str]]:
    grouped: dict[str, set[str]] = defaultdict(set)
    for entity in entities:
        entity_type = str(entity.get("entity_type") or "")
        entity_id = str(entity.get("entity_id") or "")
        if entity_type and entity_id:
            grouped[entity_type].add(entity_id)
    return grouped


def _rollback_blockers(db: Session, entities: dict[str, set[str]]) -> list[str]:
    checks = (
        ("business_location", "business_location_id"),
        ("portfolio", "portfolio_id"),
        ("campaign", "campaign_id"),
        ("keyword_cluster", "cluster_id"),
        ("campaign_keyword", "keyword_id"),
        ("competitor", "competitor_id"),
        ("directory_listing", "listing_id"),
    )
    allowed_ids = {
        "business_locations": entities.get("business_location", set()),
        "portfolios": entities.get("portfolio", set()),
        "campaigns": entities.get("campaign", set()),
        "keyword_clusters": entities.get("keyword_cluster", set()),
        "campaign_keywords": entities.get("campaign_keyword", set()),
        "competitors": entities.get("competitor", set()),
        "ranking_snapshots": entities.get("ranking_snapshot", set()),
        "directory_listings": entities.get("directory_listing", set()),
        "directory_listing_observations": entities.get(
            "directory_listing_observation", set()
        ),
        "report_recipients": entities.get("report_recipient", set()),
    }
    blockers: list[str] = []
    recipient_ids = entities.get("report_recipient", set())
    if recipient_ids:
        reviewed_recipient = (
            db.query(ReportRecipient.id)
            .filter(
                ReportRecipient.id.in_(recipient_ids),
                (
                    (ReportRecipient.enabled.is_(True))
                    | (ReportRecipient.source_type != "imported")
                ),
            )
            .first()
        )
        if reviewed_recipient is not None:
            blockers.append("report_recipients_reviewed")
    for entity_type, foreign_key_name in checks:
        parent_ids = entities.get(entity_type, set())
        if not parent_ids:
            continue
        for table in Base.metadata.sorted_tables:
            if foreign_key_name not in table.c:
                continue
            primary_key_columns = list(table.primary_key.columns)
            primary_key = primary_key_columns[0] if len(primary_key_columns) == 1 else None
            columns = [primary_key] if primary_key is not None else []
            statement = select(*columns).where(table.c[foreign_key_name].in_(parent_ids))
            rows = list(db.execute(statement).scalars()) if columns else []
            if not columns:
                exists = db.execute(
                    select(table.c[foreign_key_name])
                    .where(table.c[foreign_key_name].in_(parent_ids))
                    .limit(1)
                ).first()
                if exists:
                    blockers.append(table.name)
                continue
            allowed = allowed_ids.get(table.name, set())
            if any(str(row_id) not in allowed for row_id in rows):
                blockers.append(table.name)
    return sorted(set(blockers))


def _delete_created_entities(
    db: Session,
    organization_id: str,
    tenant_id: str,
    entities: dict[str, set[str]],
) -> None:
    model_deletes = (
        (ReportRecipient, "report_recipient"),
        (DirectoryListingObservation, "directory_listing_observation"),
        (DirectoryListing, "directory_listing"),
        (RankingSnapshot, "ranking_snapshot"),
        (Competitor, "competitor"),
        (CampaignKeyword, "campaign_keyword"),
        (KeywordCluster, "keyword_cluster"),
        (Campaign, "campaign"),
        (Portfolio, "portfolio"),
        (BusinessLocation, "business_location"),
    )
    for model, entity_type in model_deletes:
        ids = entities.get(entity_type, set())
        if not ids:
            continue
        query = db.query(model).filter(model.id.in_(ids))
        if hasattr(model, "tenant_id"):
            query = query.filter(model.tenant_id == tenant_id)
        if hasattr(model, "organization_id"):
            query = query.filter(model.organization_id == organization_id)
        query.delete(synchronize_session=False)


def _source_hash(csv_text: str) -> str:
    return hashlib.sha256(csv_text.encode("utf-8")).hexdigest()


def _review_hash(review: dict[str, Any]) -> str:
    governed = {
        "source_system": review["source_system"],
        "adapter": review["adapter"],
        "source_sha256": review["source_sha256"],
        "field_mapping": review["field_mapping"],
        "summary": review["summary"],
        "rows": review["rows"],
    }
    encoded = json.dumps(governed, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _safe_filename(value: str | None) -> str | None:
    if not value:
        return None
    return re.split(r"[/\\]", value.replace("\x00", ""))[-1].strip()[:255] or None


def _reader(
    csv_text: str,
    *,
    source_system: str,
) -> tuple[csv.DictReader, dict[str, str], list[tuple[str, str]], str]:
    sample = csv_text[:8_192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff")), dialect=dialect)
    headers = [str(value or "").strip() for value in (reader.fieldnames or [])]
    if not headers:
        raise MigrationImportError(
            "The file needs a heading row.",
            reason_code="migration_headers_missing",
        )
    normalized = {_header_key(header): header for header in headers if header}
    mapping: dict[str, str] = {}
    for canonical, aliases in FIELD_ALIASES.items():
        source_aliases = SOURCE_FIELD_ALIASES.get(source_system, {}).get(canonical, ())
        for alias in (*source_aliases, *aliases):
            original = normalized.get(alias)
            if original:
                mapping[canonical] = original
                break
    missing = [field for field in ("record_type", "location_name") if field not in mapping]
    if missing:
        raise MigrationImportError(
            "The file needs Record Type and Location Name columns.",
            reason_code="migration_required_headers_missing",
        )
    mapped_headers = set(mapping.values())
    alias_to_field = {
        alias: canonical
        for canonical, aliases in FIELD_ALIASES.items()
        for alias in (
            *SOURCE_FIELD_ALIASES.get(source_system, {}).get(canonical, ()),
            *aliases,
        )
    }
    ignored_headers: list[tuple[str, str]] = []
    for header in headers:
        if not header or header in mapped_headers:
            continue
        canonical = alias_to_field.get(_header_key(header))
        reason = (
            f"Another column is already being used for {canonical.replace('_', ' ')}."
            if canonical
            else "This column is not supported by the current importer."
        )
        ignored_headers.append((header, reason))
    adapter_name = {
        "semrush": "semrush_csv_v1",
        "brightlocal": "brightlocal_csv_v1",
    }.get(source_system, "insightos_standard_csv_v1")
    return reader, mapping, ignored_headers, adapter_name


def _canonical_row(raw_row: dict[str | None, Any], mapping: dict[str, str]) -> dict[str, str]:
    row: dict[str, str] = {}
    for field in CANONICAL_FIELDS:
        value = raw_row.get(mapping.get(field, ""), "")
        row[field] = str(value or "").strip()
    return row


def _review_row(
    *,
    row_number: int,
    row: dict[str, str],
    seen: set[tuple[str, ...]],
    file_locations: dict[str, list[dict[str, Any]]],
    file_keywords: dict[tuple[str, str], list[int]],
    locations_by_name: dict[str, list[BusinessLocation]],
    locations_by_domain: dict[str, list[BusinessLocation]],
    campaign_by_location: dict[str, Campaign],
    existing_keywords: dict[str, set[str]],
    existing_competitors: dict[str, set[str]],
    existing_rankings: dict[tuple[str, str, str], set[int]],
    existing_listing_evidence: set[tuple[str, str, str, str]],
    existing_recipients: dict[str, set[str]],
) -> dict[str, Any]:
    record_type = _record_type(row.get("record_type"))
    location_name = row.get("location_name", "").strip()
    location_key = _text_key(location_name)
    website = _domain(row.get("website"))
    issues: list[dict[str, str]] = []

    if record_type not in RECORD_TYPES:
        _issue(
            issues,
            "record_type_invalid",
            "Use location, keyword, competitor, ranking, listing, or report recipient as the record type.",
        )
    if not location_name:
        _issue(issues, "location_name_missing", "Add the location name this row belongs to.")
    if row.get("website") and not website:
        _issue(issues, "website_invalid", "Enter a website such as example.com without a page path.")
    for field, value in row.items():
        if len(value) > MAX_CELL_LENGTH:
            _issue(
                issues,
                "value_too_long",
                f"Shorten the {field.replace('_', ' ')} value to {MAX_CELL_LENGTH:,} characters or fewer.",
            )

    matched, match_issue = _match_existing_location(
        location_key=location_key,
        domain=website,
        locations_by_name=locations_by_name,
        locations_by_domain=locations_by_domain,
    )
    if match_issue:
        _issue(issues, match_issue[0], match_issue[1])

    key: tuple[str, ...]
    detail = ""
    if record_type == "location":
        if not website and matched is None:
            _issue(issues, "website_missing", "Add the website for a new location.")
        if location_key and len(file_locations.get(location_key, [])) > 1:
            _issue(
                issues,
                "location_name_repeated",
                "More than one location row uses this name. Give each location a unique name.",
            )
        key = ("location", location_key, website)
        detail = "Match this row to the saved location." if matched else "Create this location after final review."
    elif record_type == "keyword":
        phrase = row.get("phrase", "").strip()
        if not phrase:
            _issue(issues, "keyword_missing", "Add the search phrase to track.")
        elif len(phrase) > 255:
            _issue(issues, "keyword_too_long", "Keep the search phrase under 256 characters.")
        key = ("keyword", location_key, _text_key(phrase))
        detail = "Add this search phrase to the matched location."
        _assert_location_reference(issues, location_key, matched, file_locations)
        if matched is not None and not matched.domain:
            _issue(
                issues,
                "location_website_missing",
                f"Add a website to {matched.name} before importing searches.",
            )
        campaign = campaign_by_location.get(matched.id) if matched else None
        if not issues and campaign and _text_key(phrase) in existing_keywords.get(campaign.id, set()):
            return _result(row_number, record_type, row, "already_saved", matched, issues, "This search phrase is already tracked.")
    elif record_type == "competitor":
        competitor_domain = _domain(row.get("competitor_domain"))
        if not competitor_domain:
            _issue(issues, "competitor_missing", "Add a competitor website such as competitor.com.")
        key = ("competitor", location_key, competitor_domain)
        detail = "Add this competitor to the matched location."
        _assert_location_reference(issues, location_key, matched, file_locations)
        if matched is not None and not matched.domain:
            _issue(
                issues,
                "location_website_missing",
                f"Add a website to {matched.name} before importing competitors.",
            )
        campaign = campaign_by_location.get(matched.id) if matched else None
        if not issues and campaign and competitor_domain in existing_competitors.get(campaign.id, set()):
            return _result(row_number, record_type, row, "already_saved", matched, issues, "This competitor is already saved.")
    elif record_type == "ranking":
        phrase = row.get("phrase", "").strip()
        position = _parse_position(row.get("position"))
        captured_at = _parse_import_datetime(row.get("captured_at"))
        if not phrase:
            _issue(issues, "keyword_missing", "Add the search phrase for this saved ranking.")
        if position is None:
            _issue(issues, "ranking_position_invalid", "Enter a whole-number position from 1 to 1,000.")
        if captured_at is None:
            _issue(issues, "ranking_date_invalid", "Enter the original ranking date, such as 2026-07-31.")
        elif captured_at > datetime.now(UTC) + timedelta(days=1):
            _issue(issues, "ranking_date_future", "Use the date when this ranking was originally recorded.")
        _assert_location_reference(issues, location_key, matched, file_locations)
        campaign = campaign_by_location.get(matched.id) if matched else None
        existing_keyword = bool(
            campaign and _text_key(phrase) in existing_keywords.get(campaign.id, set())
        )
        keyword_rows = file_keywords.get((location_key, _text_key(phrase)), [])
        if not existing_keyword:
            if len(keyword_rows) == 0:
                _issue(
                    issues,
                    "ranking_keyword_missing",
                    "Add a keyword row for this exact search phrase before its ranking history.",
                )
            elif len(keyword_rows) > 1:
                _issue(
                    issues,
                    "ranking_keyword_ambiguous",
                    "More than one keyword row uses this phrase for the location. Keep one.",
                )
        captured_key = captured_at.isoformat() if captured_at else ""
        key = ("ranking", location_key, _text_key(phrase), captured_key)
        detail = "Add this as imported ranking history, separate from newly collected rankings."
        if not issues and campaign and captured_at and position is not None:
            saved_positions = existing_rankings.get(
                (campaign.id, _text_key(phrase), captured_key),
                set(),
            )
            if position in saved_positions:
                return _result(
                    row_number,
                    record_type,
                    row,
                    "already_saved",
                    matched,
                    issues,
                    "This historical ranking is already saved.",
                )
            if saved_positions:
                _issue(
                    issues,
                    "ranking_position_conflict",
                    "A different position is already saved for this search and date. Confirm the source file.",
                )
    elif record_type == "listing":
        directory_name = row.get("directory_name", "").strip()
        captured_at = _parse_import_datetime(row.get("captured_at"))
        listing_url = _safe_public_url(row.get("listing_url"))
        claimed_status = _listing_claim_status(row.get("listing_status"))
        if not directory_name:
            _issue(issues, "directory_name_missing", "Add the directory or public profile name.")
        if row.get("listing_url") and not listing_url:
            _issue(issues, "listing_url_invalid", "Enter the full public listing link, including https://.")
        if captured_at is None:
            _issue(issues, "listing_date_invalid", "Enter the date this listing information was collected.")
        elif captured_at > datetime.now(UTC) + timedelta(days=1):
            _issue(issues, "listing_date_future", "Use the date this listing information was originally collected.")
        if claimed_status is None:
            _issue(
                issues,
                "listing_status_invalid",
                "Use live, verified, correct, inconsistent, missing, duplicate, submitted, or unavailable.",
            )
        importance = _text_key(row.get("directory_importance")) or "unknown"
        if importance not in {"essential", "important", "standard", "unknown"}:
            _issue(
                issues,
                "listing_importance_invalid",
                "Use essential, important, standard, or unknown for directory importance.",
            )
        _assert_location_reference(issues, location_key, matched, file_locations)
        captured_key = captured_at.isoformat() if captured_at else ""
        identity = row.get("source_record_id") or listing_url or ""
        key = ("listing", location_key, _text_key(directory_name), captured_key, identity)
        detail = (
            "Save this as imported listing history. It will not count as a fresh public listing check."
        )
        if not issues and matched is not None and captured_at is not None:
            evidence_key = _listing_evidence_key(
                location_id=matched.id,
                directory_name=directory_name,
                captured_at=captured_at,
                source_record_id=row.get("source_record_id"),
                listing_url=listing_url,
            )
            if evidence_key in existing_listing_evidence:
                return _result(
                    row_number,
                    record_type,
                    row,
                    "already_saved",
                    matched,
                    issues,
                    "This imported listing record is already saved.",
                )
    elif record_type == "report_recipient":
        email = _normalized_email(row.get("recipient_email"))
        role = _recipient_role(row.get("recipient_role"))
        if email is None:
            _issue(issues, "recipient_email_invalid", "Enter a complete report email address.")
        if role is None:
            _issue(issues, "recipient_role_invalid", "Use owner, manager, or client as the recipient role.")
        if len(row.get("recipient_name", "")) > 160:
            _issue(issues, "recipient_name_too_long", "Keep the recipient name under 161 characters.")
        _assert_location_reference(issues, location_key, matched, file_locations)
        key = ("report_recipient", location_key, email or "")
        detail = (
            "Save this report recipient in the off position. No report will be sent until an owner turns it on."
        )
        campaign = campaign_by_location.get(matched.id) if matched else None
        if not issues and campaign and email in existing_recipients.get(campaign.id, set()):
            return _result(
                row_number,
                record_type,
                row,
                "already_saved",
                matched,
                issues,
                "This report recipient is already saved for the location.",
            )
    else:
        key = ("invalid", str(row_number))

    if key in seen:
        return _result(row_number, record_type, row, "duplicate", matched, issues, "This row repeats an earlier row in the file.")
    seen.add(key)
    if issues:
        return _result(row_number, record_type, row, "needs_attention", matched, issues, "Fix this row before importing.")
    if record_type == "location" and matched:
        return _result(row_number, record_type, row, "already_saved", matched, issues, "This location is already saved.")
    return _result(row_number, record_type, row, "ready", matched, issues, detail)


def _assert_location_reference(
    issues: list[dict[str, str]],
    location_key: str,
    matched: BusinessLocation | None,
    file_locations: dict[str, list[dict[str, Any]]],
) -> None:
    if matched is not None:
        return
    matches = file_locations.get(location_key, [])
    if len(matches) == 1:
        return
    if len(matches) > 1:
        _issue(issues, "location_reference_ambiguous", "More than one location row uses this name. Make each location name unique.")
    else:
        _issue(issues, "location_reference_missing", "Add a location row with this exact location name first.")


def _match_existing_location(
    *,
    location_key: str,
    domain: str,
    locations_by_name: dict[str, list[BusinessLocation]],
    locations_by_domain: dict[str, list[BusinessLocation]],
) -> tuple[BusinessLocation | None, tuple[str, str] | None]:
    domain_matches = locations_by_domain.get(domain, []) if domain else []
    if len(domain_matches) == 1:
        location = domain_matches[0]
        if location_key and _text_key(location.name) != location_key:
            return location, (
                "location_name_differs",
                f"This website is already saved as {location.name}. Confirm which name should be kept.",
            )
        return location, None
    if len(domain_matches) > 1:
        return None, ("location_match_ambiguous", "This website matches more than one saved location.")
    name_matches = locations_by_name.get(location_key, []) if location_key else []
    if len(name_matches) == 1:
        location = name_matches[0]
        saved_domain = _domain(location.domain)
        if domain and saved_domain and domain != saved_domain:
            return location, (
                "location_website_differs",
                f"{location.name} is already connected to {saved_domain}. Confirm the correct website.",
            )
        return location, None
    if len(name_matches) > 1:
        return None, ("location_match_ambiguous", "This name matches more than one saved location.")
    return None, None


def _result(
    row_number: int,
    record_type: str,
    row: dict[str, str],
    status: str,
    matched: BusinessLocation | None,
    issues: list[dict[str, str]],
    detail: str,
) -> dict[str, Any]:
    return {
        "row_number": row_number,
        "record_type": record_type,
        "location_name": row.get("location_name", ""),
        "status": status,
        "detail": detail,
        "matched_location_id": matched.id if matched else None,
        "matched_location_name": matched.name if matched else None,
        "values": {field: value[:500] for field, value in row.items() if value},
        "issues": issues,
    }


def _issue(issues: list[dict[str, str]], code: str, message: str) -> None:
    if code not in {item["code"] for item in issues}:
        issues.append({"code": code, "message": message})


def _record_type(value: Any) -> str:
    normalized = _text_key(str(value or "")).replace(" ", "_")
    return {
        "rank": "ranking",
        "rank_history": "ranking",
        "ranking_history": "ranking",
        "historical_rank": "ranking",
        "citation": "listing",
        "directory_listing": "listing",
        "listing_history": "listing",
        "recipient": "report_recipient",
        "report_email": "report_recipient",
        "report_recipient_email": "report_recipient",
    }.get(normalized, normalized)


def _parse_position(value: Any) -> int | None:
    raw = str(value or "").strip()
    if not re.fullmatch(r"\d{1,4}", raw):
        return None
    parsed = int(raw)
    return parsed if 1 <= parsed <= 1_000 else None


def _parse_import_datetime(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        parsed = None
    if parsed is None:
        for pattern in ("%m/%d/%Y", "%m/%d/%Y %H:%M", "%Y/%m/%d"):
            try:
                parsed = datetime.strptime(raw, pattern)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    return _as_utc(parsed)


def _listing_claim_status(value: Any) -> str | None:
    normalized = _text_key(value).replace(" ", "_")
    aliases = {
        "": "unavailable",
        "active": "live",
        "present": "live",
        "claimed": "live",
        "accurate": "correct",
        "incorrect": "inconsistent",
        "not_found": "missing",
        "pending": "submitted",
    }
    normalized = aliases.get(normalized, normalized)
    allowed = {
        "correct",
        "inconsistent",
        "missing",
        "duplicate",
        "submitted",
        "live",
        "verified",
        "unavailable",
    }
    return normalized if normalized in allowed else None


def _normalized_email(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    if not normalized or len(normalized) > 320:
        return None
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized):
        return None
    return normalized


def _recipient_role(value: Any) -> str | None:
    normalized = _text_key(value).replace(" ", "_")
    normalized = {
        "": "client",
        "customer": "client",
        "business_owner": "owner",
        "admin": "manager",
        "location_manager": "manager",
    }.get(normalized, normalized)
    return normalized if normalized in {"owner", "manager", "client"} else None


def _safe_public_url(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return raw[:1_000]


def _listing_evidence_key(
    *,
    location_id: str,
    directory_name: str,
    captured_at: datetime,
    source_record_id: Any,
    listing_url: Any,
) -> tuple[str, str, str, str]:
    identity = str(source_record_id or listing_url or "").strip().casefold()
    return (
        str(location_id),
        _text_key(directory_name),
        _as_utc(captured_at).isoformat(),
        identity,
    )


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _text_key(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _header_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _domain(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    candidate = raw if "://" in raw else f"https://{raw}"
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return ""
    host = (parsed.hostname or "").strip(".").lower()
    if (
        not host
        or "." not in host
        or ".." in host
        or not re.fullmatch(r"[a-z0-9.-]+", host)
    ):
        return ""
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        return ""
    return host[4:] if host.startswith("www.") else host
