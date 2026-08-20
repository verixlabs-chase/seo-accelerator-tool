from __future__ import annotations

import json
import re
import unicodedata
from hashlib import sha256
from io import BytesIO
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from sqlalchemy.orm import Session

from app.services import report_pdf_service, reporting_service
from app.services.audit_service import write_audit_log
from app.services.commercial_plan_service import (
    FEATURE_CLIENT_REPORT_PACKAGE,
    require_commercial_feature,
)


PACKAGE_SCHEMA_VERSION = "ent1-client-report-package-v1"
MAX_PACKAGE_REPORTS = 20
MAX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
MAX_PDF_BYTES = 20 * 1024 * 1024
_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


class EnterpriseReportExportError(ValueError):
    def __init__(self, message: str, *, reason_code: str, status_code: int = 409) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.status_code = status_code


def _safe_filename(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    return (slug[:48].rstrip("-") or "location") + ".pdf"


def _zip_entry(name: str, content: bytes) -> tuple[ZipInfo, bytes]:
    info = ZipInfo(filename=name, date_time=_ZIP_TIMESTAMP)
    info.compress_type = ZIP_DEFLATED
    info.external_attr = 0o600 << 16
    return info, content


def _verified_pdf(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    report_id: str,
) -> bytes:
    artifacts = reporting_service.get_report_artifacts(
        db,
        tenant_id=tenant_id,
        report_id=report_id,
        organization_id=organization_id,
    )
    pdf = next(
        (
            artifact
            for artifact in artifacts
            if artifact.artifact_type == "pdf"
            and reporting_service.artifact_contract(artifact)["ready"]
        ),
        None,
    )
    if pdf is None:
        raise EnterpriseReportExportError(
            "Every included location needs a verified PDF before this package can be downloaded.",
            reason_code="client_report_package_pdf_missing",
        )
    if pdf.byte_size is not None and pdf.byte_size > MAX_PDF_BYTES:
        raise EnterpriseReportExportError(
            "A saved location PDF is too large to include safely in this package.",
            reason_code="client_report_package_pdf_too_large",
        )
    _, content = reporting_service.read_report_artifact(
        db,
        tenant_id=tenant_id,
        report_id=report_id,
        artifact_id=pdf.id,
        organization_id=organization_id,
    )
    if not content.startswith(b"%PDF-"):
        raise EnterpriseReportExportError(
            "A saved report file did not pass the package file check.",
            reason_code="client_report_package_pdf_invalid",
        )
    if len(content) > MAX_PDF_BYTES:
        raise EnterpriseReportExportError(
            "A saved location PDF is too large to include safely in this package.",
            reason_code="client_report_package_pdf_too_large",
        )
    return content


def build_client_report_package(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    actor_user_id: str,
) -> dict[str, Any]:
    if tenant_id != organization_id:
        raise EnterpriseReportExportError(
            "Organization context does not match this request.",
            reason_code="organization_scope_mismatch",
            status_code=404,
        )
    require_commercial_feature(
        db,
        organization_id=organization_id,
        feature_code=FEATURE_CLIENT_REPORT_PACKAGE,
    )
    snapshot = reporting_service.build_portfolio_report_snapshot(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
    )
    locations = sorted(
        snapshot.get("locations") or [],
        key=lambda item: (str(item.get("location_name") or "").lower(), str(item.get("report", {}).get("id") or "")),
    )
    if not locations or len(locations) > MAX_PACKAGE_REPORTS:
        raise EnterpriseReportExportError(
            "A client report package can include between 1 and 20 verified location reports.",
            reason_code="client_report_package_report_count_invalid",
        )

    portfolio_pdf = report_pdf_service.build_portfolio_report_pdf(snapshot)
    files: list[tuple[str, bytes]] = [("portfolio-summary.pdf", portfolio_pdf)]
    manifest_reports: list[dict[str, Any]] = []
    used_names: set[str] = set()
    for index, location in enumerate(locations, start=1):
        report = location.get("report") or {}
        report_id = str(report.get("id") or "")
        if not report_id:
            raise EnterpriseReportExportError(
                "A saved location report is missing its report identity.",
                reason_code="client_report_package_report_invalid",
            )
        content = _verified_pdf(
            db,
            tenant_id=tenant_id,
            organization_id=organization_id,
            report_id=report_id,
        )
        filename = _safe_filename(str(location.get("location_name") or "location"))
        if filename in used_names:
            filename = f"{filename[:-4]}-{index}.pdf"
        used_names.add(filename)
        archive_path = f"location-reports/{filename}"
        files.append((archive_path, content))
        manifest_reports.append(
            {
                "file": archive_path,
                "location": str(location.get("location_name") or "Location"),
                "website": str(location.get("domain") or "") or None,
                "period": location.get("period") or {},
                "saved_report_generated_at": report.get("generated_at"),
                "saved_report_snapshot_sha256": report.get("snapshot_hash"),
                "file_sha256": sha256(content).hexdigest(),
                "bytes": len(content),
            }
        )

    total_bytes = sum(len(content) for _, content in files)
    if total_bytes > MAX_UNCOMPRESSED_BYTES:
        raise EnterpriseReportExportError(
            "This report package is too large to prepare safely. Download the location reports separately.",
            reason_code="client_report_package_too_large",
        )

    brand = snapshot.get("brand") or {}
    manifest = {
        "schema_version": PACKAGE_SCHEMA_VERSION,
        "source_contract": "verified_saved_report_pdfs_and_frozen_snapshots",
        "assembled_from_snapshot_at": snapshot.get("assembled_at"),
        "portfolio_snapshot_sha256": snapshot.get("snapshot_hash"),
        "organization": snapshot.get("organization", {}).get("name"),
        "period": snapshot.get("period") or {},
        "report_count": len(manifest_reports),
        "totals_are_combined": False,
        "branding": {
            "brand_name": brand.get("brand_name"),
            "report_title": brand.get("report_title"),
            "accent_color": brand.get("accent_color"),
            "logo_sha256": brand.get("logo_sha256"),
            "platform_attribution_shown": brand.get("show_platform_attribution"),
        },
        "files": [
            {
                "file": "portfolio-summary.pdf",
                "file_sha256": sha256(portfolio_pdf).hexdigest(),
                "bytes": len(portfolio_pdf),
            },
            *manifest_reports,
        ],
    }
    manifest_content = json.dumps(manifest, indent=2, sort_keys=True, default=str).encode("utf-8")
    if total_bytes + len(manifest_content) > MAX_UNCOMPRESSED_BYTES:
        raise EnterpriseReportExportError(
            "This report package is too large to prepare safely. Download the location reports separately.",
            reason_code="client_report_package_too_large",
        )

    buffer = BytesIO()
    with ZipFile(buffer, mode="w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for name, content in [
            ("manifest.json", manifest_content),
            *files,
        ]:
            info, verified_content = _zip_entry(name, content)
            archive.writestr(info, verified_content, compress_type=ZIP_DEFLATED, compresslevel=9)
    package = buffer.getvalue()
    digest = sha256(package).hexdigest()

    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        event_type="enterprise.client_report_package.downloaded",
        payload={
            "organization_id": organization_id,
            "report_count": len(manifest_reports),
            "portfolio_snapshot_sha256": snapshot.get("snapshot_hash"),
            "package_sha256": digest,
            "package_bytes": len(package),
        },
    )
    db.commit()
    return {
        "content": package,
        "sha256": digest,
        "report_count": len(manifest_reports),
        "filename": "insightos-client-report-package.zip",
    }
