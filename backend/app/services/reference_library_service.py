import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.audit_log import AuditLog
from app.models.reference_library import (
    ReferenceLibraryActivation,
    ReferenceLibraryArtifact,
    ReferenceLibraryValidationRun,
    ReferenceLibraryVersion,
)
from app.reference_library.schema_models import MetricsArtifact, RecommendationsArtifact


def _now() -> datetime:
    return datetime.now(UTC)


def _root_dir() -> Path:
    return Path(__file__).resolve().parents[3]


def _seed_dir() -> Path:
    settings = get_settings()
    if settings.reference_library_seed_path.strip():
        return Path(settings.reference_library_seed_path).expanduser().resolve()
    return _root_dir() / "Docs" / "TXT Governing Docs" / "Future Enhancements" / "reference_library"


def _seed_file(relative: str) -> Path:
    candidate = _seed_dir() / relative
    if not candidate.exists():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Reference library artifact missing: {relative}",
        )
    return candidate


def _load_default_artifacts() -> dict[str, Any]:
    metrics_path = _seed_file("metrics/core_web_vitals.json")
    recommendations_path = _seed_file("recommendations/perf_recommendations.json")
    return {
        "metrics": json.loads(metrics_path.read_text(encoding="utf-8")),
        "recommendations": json.loads(recommendations_path.read_text(encoding="utf-8")),
        "_source": {
            "metrics": str(metrics_path),
            "recommendations": str(recommendations_path),
        },
    }


def _digest(payload: Any) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def _validate_bundle(artifacts: dict[str, Any], strict_mode: bool) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    metrics_payload = artifacts.get("metrics")
    recommendations_payload = artifacts.get("recommendations")
    if not isinstance(metrics_payload, dict):
        errors.append("Missing `metrics` artifact object.")
    if not isinstance(recommendations_payload, dict):
        errors.append("Missing `recommendations` artifact object.")
    if errors:
        return errors, warnings
    assert isinstance(metrics_payload, dict)
    assert isinstance(recommendations_payload, dict)

    enforce_validation = get_settings().reference_library_enforce_validation
    if enforce_validation:
        try:
            MetricsArtifact.model_validate(metrics_payload)
        except ValidationError as exc:
            errors.append(f"`metrics` artifact schema validation failed: {exc.errors()}")
        try:
            RecommendationsArtifact.model_validate(recommendations_payload)
        except ValidationError as exc:
            errors.append(f"`recommendations` artifact schema validation failed: {exc.errors()}")
        if errors:
            return errors, warnings

    metric_rows = metrics_payload.get("metrics")
    rec_rows = recommendations_payload.get("recommendations")
    if not isinstance(metric_rows, list):
        errors.append("`metrics.metrics` must be a list.")
        return errors, warnings
    if not isinstance(rec_rows, list):
        errors.append("`recommendations.recommendations` must be a list.")
        return errors, warnings

    rec_keys = {row.get("rec_key") for row in rec_rows if isinstance(row, dict)}
    for idx, row in enumerate(metric_rows):
        if not isinstance(row, dict):
            errors.append(f"`metrics.metrics[{idx}]` must be an object.")
            continue
        metric_key = row.get("metric_key")
        if not isinstance(metric_key, str) or not metric_key.strip():
            errors.append(f"`metrics.metrics[{idx}].metric_key` is required.")

        thresholds = row.get("thresholds")
        if not isinstance(thresholds, dict):
            errors.append(f"`metrics.metrics[{idx}].thresholds` is required.")
        else:
            for key in ("good", "needs_improvement", "units"):
                if key not in thresholds:
                    errors.append(f"`metrics.metrics[{idx}].thresholds.{key}` is required.")

        refs = row.get("recommendations")
        if not isinstance(refs, list):
            errors.append(f"`metrics.metrics[{idx}].recommendations` must be a list.")
            continue
        for rec_key in refs:
            if rec_key not in rec_keys:
                errors.append(f"Unknown recommendation key `{rec_key}` linked from `{metric_key}`.")

    effective_strict_mode = strict_mode or get_settings().reference_library_enforce_validation
    if effective_strict_mode:
        for idx, row in enumerate(rec_rows):
            if not isinstance(row, dict):
                errors.append(f"`recommendations.recommendations[{idx}]` must be an object.")
                continue
            for key in ("rec_key", "impact", "effort", "risk_tier"):
                if key not in row:
                    errors.append(f"`recommendations.recommendations[{idx}].{key}` is required.")
    else:
        warnings.append("Validation ran in non-strict mode.")

    return errors, warnings


def _write_audit_log(db: Session, tenant_id: str, actor_user_id: str | None, event_type: str, payload: dict[str, Any]) -> None:
    db.add(
        AuditLog(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            event_type=event_type,
            payload_json=json.dumps(payload),
            created_at=_now(),
        )
    )


def validate_version(
    db: Session,
    tenant_id: str,
    actor_user_id: str,
    version: str,
    artifacts: dict[str, Any] | None,
    strict_mode: bool,
) -> dict[str, Any]:
    payload = artifacts or _load_default_artifacts()
    errors, warnings = _validate_bundle(payload, strict_mode=strict_mode)

    row = (
        db.query(ReferenceLibraryVersion)
        .filter(ReferenceLibraryVersion.tenant_id == tenant_id, ReferenceLibraryVersion.version == version)
        .first()
    )
    if row is None:
        row = ReferenceLibraryVersion(
            tenant_id=tenant_id,
            version=version,
            status="draft",
            created_by=actor_user_id,
        )
        db.add(row)
        db.flush()

    row.status = "validated" if not errors else "draft"
    row.updated_at = _now()

    metrics_payload = payload.get("metrics")
    recommendations_payload = payload.get("recommendations")
    sources = payload.get("_source", {}) if isinstance(payload.get("_source"), dict) else {}
    schema_version = "v1"

    if isinstance(metrics_payload, dict):
        metrics_artifact = (
            db.query(ReferenceLibraryArtifact)
            .filter(
                ReferenceLibraryArtifact.tenant_id == tenant_id,
                ReferenceLibraryArtifact.reference_library_version_id == row.id,
                ReferenceLibraryArtifact.artifact_type == "metrics",
            )
            .first()
        )
        if metrics_artifact is None:
            metrics_artifact = ReferenceLibraryArtifact(
                tenant_id=tenant_id,
                reference_library_version_id=row.id,
                artifact_type="metrics",
                artifact_uri=str(sources.get("metrics", "inline://metrics")),
                artifact_sha256=_digest(metrics_payload),
                schema_version=schema_version,
            )
            db.add(metrics_artifact)
        else:
            metrics_artifact.artifact_uri = str(sources.get("metrics", metrics_artifact.artifact_uri))
            metrics_artifact.artifact_sha256 = _digest(metrics_payload)
            metrics_artifact.schema_version = schema_version

    if isinstance(recommendations_payload, dict):
        rec_artifact = (
            db.query(ReferenceLibraryArtifact)
            .filter(
                ReferenceLibraryArtifact.tenant_id == tenant_id,
                ReferenceLibraryArtifact.reference_library_version_id == row.id,
                ReferenceLibraryArtifact.artifact_type == "recommendations",
            )
            .first()
        )
        if rec_artifact is None:
            rec_artifact = ReferenceLibraryArtifact(
                tenant_id=tenant_id,
                reference_library_version_id=row.id,
                artifact_type="recommendations",
                artifact_uri=str(sources.get("recommendations", "inline://recommendations")),
                artifact_sha256=_digest(recommendations_payload),
                schema_version=schema_version,
            )
            db.add(rec_artifact)
        else:
            rec_artifact.artifact_uri = str(sources.get("recommendations", rec_artifact.artifact_uri))
            rec_artifact.artifact_sha256 = _digest(recommendations_payload)
            rec_artifact.schema_version = schema_version

    run = ReferenceLibraryValidationRun(
        tenant_id=tenant_id,
        reference_library_version_id=row.id,
        status="passed" if not errors else "failed",
        errors_json=json.dumps(errors),
        warnings_json=json.dumps(warnings),
    )
    db.add(run)
    _write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        event_type="reference_library.validate",
        payload={"version": version, "status": run.status, "errors": len(errors), "warnings": len(warnings)},
    )
    db.commit()
    return {
        "validation_run_id": run.id,
        "status": run.status,
        "errors": errors,
        "warnings": warnings,
    }


def activate_version(db: Session, tenant_id: str, actor_user_id: str, version: str, reason: str | None) -> dict[str, Any]:
    row = (
        db.query(ReferenceLibraryVersion)
        .filter(ReferenceLibraryVersion.tenant_id == tenant_id, ReferenceLibraryVersion.version == version)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reference library version not found")
    latest_validation = (
        db.query(ReferenceLibraryValidationRun)
        .filter(
            ReferenceLibraryValidationRun.tenant_id == tenant_id,
            ReferenceLibraryValidationRun.reference_library_version_id == row.id,
        )
        .order_by(ReferenceLibraryValidationRun.executed_at.desc())
        .first()
    )
    if latest_validation is None or latest_validation.status.lower() != "passed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Activation blocked: latest validation status is not PASSED",
        )
    if row.status not in {"validated", "active"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Reference library version is not validated")

    previous = (
        db.query(ReferenceLibraryVersion)
        .filter(ReferenceLibraryVersion.tenant_id == tenant_id, ReferenceLibraryVersion.status == "active")
        .first()
    )
    if previous is not None and previous.id != row.id:
        previous.status = "validated"
        previous.updated_at = _now()

    row.status = "active"
    row.updated_at = _now()

    activation = ReferenceLibraryActivation(
        tenant_id=tenant_id,
        reference_library_version_id=row.id,
        activated_by=actor_user_id,
        rollback_from_version=previous.version if previous is not None and previous.id != row.id else None,
        activation_status="active",
    )
    db.add(activation)
    _write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        event_type="reference_library.activate",
        payload={"version": version, "reason": reason or "", "rollback_from_version": activation.rollback_from_version},
    )
    db.commit()
    return {"activation_id": activation.id, "version": version, "status": activation.activation_status}


def list_versions(db: Session, tenant_id: str) -> list[ReferenceLibraryVersion]:
    return (
        db.query(ReferenceLibraryVersion)
        .filter(ReferenceLibraryVersion.tenant_id == tenant_id)
        .order_by(ReferenceLibraryVersion.updated_at.desc())
        .all()
    )


def get_active(db: Session, tenant_id: str) -> dict[str, Any]:
    row = (
        db.query(ReferenceLibraryVersion)
        .filter(ReferenceLibraryVersion.tenant_id == tenant_id, ReferenceLibraryVersion.status == "active")
        .order_by(ReferenceLibraryVersion.updated_at.desc())
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active reference library version")
    activation = (
        db.query(ReferenceLibraryActivation)
        .filter(
            ReferenceLibraryActivation.tenant_id == tenant_id,
            ReferenceLibraryActivation.reference_library_version_id == row.id,
            ReferenceLibraryActivation.activation_status == "active",
        )
        .order_by(ReferenceLibraryActivation.created_at.desc())
        .first()
    )
    activated_at = activation.created_at if activation is not None else row.updated_at
    activated_by = activation.activated_by if activation is not None else None
    return {"version": row.version, "activated_at": activated_at, "activated_by": activated_by}
