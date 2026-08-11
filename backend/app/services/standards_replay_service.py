from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
import json
import re
from typing import Any

from sqlalchemy.orm import Session

from app.models.provider_metric_contract import ProviderMetricContractVersion
from app.models.reference_library import (
    ReferenceLibraryArtifact,
    ReferenceLibraryVersion,
    StandardsChangeCandidate,
    StandardsImpactLink,
    StandardsSourceRegistry,
)
from app.models.standards_replay import StandardsReplayReport
from app.services import metric_contract_service


REPLAY_VERSION = "i1.6d.v1"
FIXTURE_SET_VERSION = "google-objective-metrics.v1"
SUPPORTED_SAMPLE_TYPES = frozenset({"fixed_fixture", "approved_evidence", "combined"})
CONTRACT_CHANGE_FIELDS = frozenset(
    {
        "provider_name",
        "metric_family",
        "metric_id",
        "display_name",
        "definition",
        "unit",
        "aggregation",
        "direction",
        "collection_status",
        "authoritative_source_id",
        "required_scope_fields",
        "optional_scope_fields",
        "comparison_keys",
        "freshness_days",
    }
)
CONTRACT_BOUNDARY_FIELDS = frozenset(
    {
        "provider_name",
        "metric_id",
        "unit",
        "aggregation",
        "direction",
        "collection_status",
        "required_scope_fields",
        "comparison_keys",
    }
)
LEXICON_BOUNDARY_FIELDS = frozenset(
    {"kind", "unit", "aggregation", "scope", "segment_by", "source_metric_keys"}
)
VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$")


class StandardsReplayError(ValueError):
    pass


def create_metric_contract_candidate(
    db: Session,
    *,
    standards_change_candidate_id: str,
    contract_id: str,
    candidate_version: str,
    changes: dict[str, Any],
    actor_user_id: str,
    effective_at: datetime | None = None,
) -> dict[str, Any]:
    """Create an inactive metric-contract version from a reviewed published change."""

    metric_contract_service.ensure_default_contracts(db)
    change = db.get(StandardsChangeCandidate, standards_change_candidate_id)
    if change is None:
        raise StandardsReplayError("Standards change candidate was not found.")
    if change.status != "requires_contract_update":
        raise StandardsReplayError(
            "Review the published change as requiring a contract update before proposing a version."
        )
    version = candidate_version.strip()
    if not VERSION_PATTERN.fullmatch(version):
        raise StandardsReplayError("Use a short version containing letters, numbers, dots, or dashes.")
    if not isinstance(changes, dict) or not changes:
        raise StandardsReplayError("At least one metric-contract field must change.")
    unknown = sorted(set(changes) - CONTRACT_CHANGE_FIELDS)
    if unknown:
        raise StandardsReplayError(f"Unsupported metric-contract fields: {', '.join(unknown)}.")

    base = (
        db.query(ProviderMetricContractVersion)
        .filter(
            ProviderMetricContractVersion.contract_id == contract_id.strip(),
            ProviderMetricContractVersion.is_active.is_(True),
        )
        .order_by(ProviderMetricContractVersion.effective_at.desc())
        .first()
    )
    if base is None:
        raise StandardsReplayError("Active metric contract was not found.")
    existing = (
        db.query(ProviderMetricContractVersion)
        .filter(
            ProviderMetricContractVersion.contract_id == base.contract_id,
            ProviderMetricContractVersion.version == version,
        )
        .one_or_none()
    )
    if existing is not None:
        raise StandardsReplayError("That candidate contract version already exists.")
    if version == base.version:
        raise StandardsReplayError("A candidate must use a new version.")

    base_payload = _contract_definition_payload(base)
    candidate_payload = {**base_payload, **_normalize_contract_changes(changes)}
    _validate_contract_payload(db, candidate_payload)
    definition_diff = _object_diff(base_payload, candidate_payload)
    if not definition_diff:
        raise StandardsReplayError("The candidate has no definition changes.")

    proposed_at = datetime.now(UTC)
    row = ProviderMetricContractVersion(
        contract_id=base.contract_id,
        version=version,
        **candidate_payload,
        content_hash=_stable_hash(candidate_payload),
        is_active=False,
        lifecycle_status="candidate",
        supersedes_version_id=base.id,
        standards_change_candidate_id=change.id,
        proposed_by_user_id=actor_user_id,
        proposed_at=proposed_at,
        automatic_activation_allowed=False,
        effective_at=effective_at or proposed_at,
        created_at=proposed_at,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "candidate": _contract_candidate_payload(row),
        "base": _contract_candidate_payload(base),
        "definition_diff": definition_diff,
        "comparison_boundary": _contract_comparison_boundary(definition_diff),
        "automatic_activation_allowed": False,
    }


def replay_metric_contract_candidate(
    db: Session,
    *,
    candidate_contract_version_id: str,
    actor_user_id: str,
    sample_type: str = "fixed_fixture",
    evidence_samples: list[dict[str, Any]] | None = None,
    approval_reference: str | None = None,
) -> dict[str, Any]:
    candidate = db.get(ProviderMetricContractVersion, candidate_contract_version_id)
    if candidate is None or candidate.lifecycle_status != "candidate" or candidate.is_active:
        raise StandardsReplayError("Inactive candidate metric contract was not found.")
    base = db.get(ProviderMetricContractVersion, candidate.supersedes_version_id)
    if base is None:
        raise StandardsReplayError("The candidate's base contract version was not found.")
    resolved_sample_type, sanitized = _validated_samples(
        sample_type, evidence_samples or [], approval_reference
    )
    base_payload = _contract_definition_payload(base)
    candidate_payload = _contract_definition_payload(candidate)
    definition_diff = _object_diff(base_payload, candidate_payload)
    boundary = _contract_comparison_boundary(definition_diff)
    fixtures = _contract_fixed_fixtures() if resolved_sample_type != "approved_evidence" else []
    samples = fixtures + (sanitized if resolved_sample_type != "fixed_fixture" else [])
    results = [
        _contract_case_result(
            case_index=index,
            sample=sample,
            base=base,
            candidate=candidate,
            boundary=boundary,
            source="fixed_fixture" if index <= len(fixtures) else "approved_evidence",
        )
        for index, sample in enumerate(samples, start=1)
    ]
    impacts = _impact_report(
        db,
        change_candidate_id=candidate.standards_change_candidate_id,
        semantic_change=bool(definition_diff),
        comparison_boundary=boundary,
    )
    return _save_report(
        db,
        actor_user_id=actor_user_id,
        standards_change_candidate_id=candidate.standards_change_candidate_id,
        provider_metric_contract_version_id=candidate.id,
        reference_library_version_id=None,
        artifact_type="provider_metric_contract",
        artifact_key=candidate.contract_id,
        base_version=base.version,
        candidate_version=candidate.version,
        sample_type=resolved_sample_type,
        samples=sanitized,
        approval_reference=approval_reference,
        definition_diff=definition_diff,
        impact_report=impacts,
        results=results,
        requires_new_baseline=boundary["required"],
    )


def replay_lexicon_candidate(
    db: Session,
    *,
    tenant_id: str,
    candidate_version: str,
    actor_user_id: str,
    base_version: str | None = None,
    standards_change_candidate_id: str | None = None,
    sample_type: str = "fixed_fixture",
    evidence_samples: list[dict[str, Any]] | None = None,
    approval_reference: str | None = None,
) -> dict[str, Any]:
    candidate = _reference_version(db, tenant_id, candidate_version)
    if candidate.status != "validated":
        raise StandardsReplayError("The candidate lexicon must pass validation before replay.")
    base = (
        _reference_version(db, tenant_id, base_version)
        if base_version
        else db.query(ReferenceLibraryVersion)
        .filter(
            ReferenceLibraryVersion.tenant_id == tenant_id,
            ReferenceLibraryVersion.status == "active",
        )
        .order_by(ReferenceLibraryVersion.updated_at.desc())
        .first()
    )
    if base is None:
        raise StandardsReplayError("An active or explicitly selected base lexicon is required.")
    if base.id == candidate.id:
        raise StandardsReplayError("The candidate and base lexicon versions must differ.")
    if standards_change_candidate_id:
        change = db.get(StandardsChangeCandidate, standards_change_candidate_id)
        if change is None or change.status != "requires_contract_update":
            raise StandardsReplayError(
                "The linked standards change must be reviewed as requiring a contract update."
            )

    resolved_sample_type, sanitized = _validated_samples(
        sample_type, evidence_samples or [], approval_reference, lexicon=True
    )
    base_payload = _lexicon_payload(db, base)
    candidate_payload = _lexicon_payload(db, candidate)
    definition_diff, changed_items = _lexicon_diff(base_payload, candidate_payload)
    fixtures = (
        _lexicon_fixed_fixtures(base_payload, candidate_payload, changed_items)
        if resolved_sample_type != "approved_evidence"
        else []
    )
    approved = sanitized if resolved_sample_type != "fixed_fixture" else []
    results = fixtures + [
        _lexicon_evidence_result(index, sample, base_payload, candidate_payload)
        for index, sample in enumerate(approved, start=1)
    ]
    boundary = _lexicon_boundary(changed_items)
    impact_report = {
        "diagnoses": changed_items["diagnostics"],
        "actions": changed_items["actions"],
        "forecasts": [],
        "policies": changed_items["policies"],
        "comparison_boundary": boundary,
    }
    return _save_report(
        db,
        actor_user_id=actor_user_id,
        standards_change_candidate_id=standards_change_candidate_id,
        provider_metric_contract_version_id=None,
        reference_library_version_id=candidate.id,
        artifact_type="intelligence_lexicon",
        artifact_key="seo_intelligence",
        base_version=base.version,
        candidate_version=candidate.version,
        sample_type=resolved_sample_type,
        samples=sanitized,
        approval_reference=approval_reference,
        definition_diff=definition_diff,
        impact_report=impact_report,
        results=results,
        requires_new_baseline=boundary["required"],
    )


def list_replay_reports(db: Session, *, limit: int = 100) -> dict[str, Any]:
    rows = (
        db.query(StandardsReplayReport)
        .order_by(StandardsReplayReport.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "items": [_report_payload(row, include_detail=False) for row in rows],
        "returned": len(rows),
        "automatic_activation_allowed": False,
    }


def get_replay_report(db: Session, report_id: str) -> dict[str, Any] | None:
    row = db.get(StandardsReplayReport, report_id)
    return _report_payload(row, include_detail=True) if row else None


def _save_report(
    db: Session,
    *,
    actor_user_id: str,
    standards_change_candidate_id: str | None,
    provider_metric_contract_version_id: str | None,
    reference_library_version_id: str | None,
    artifact_type: str,
    artifact_key: str,
    base_version: str,
    candidate_version: str,
    sample_type: str,
    samples: list[dict[str, Any]],
    approval_reference: str | None,
    definition_diff: dict[str, Any],
    impact_report: dict[str, Any],
    results: list[dict[str, Any]],
    requires_new_baseline: bool,
) -> dict[str, Any]:
    changed_results = sum(item.get("changed") is True for item in results)
    newly_unknown = sum(item.get("candidate_result") == "unknown" for item in results)
    invalidated = sum(item.get("comparison_valid") is False for item in results)
    changed_diagnoses = _changed_surface_count(impact_report.get("diagnoses", []))
    changed_actions = _changed_surface_count(impact_report.get("actions", []))
    changed_forecasts = _changed_surface_count(impact_report.get("forecasts", []))
    status = "changed" if any(
        (changed_results, invalidated, changed_diagnoses, changed_actions, changed_forecasts)
    ) else "passed"
    row = StandardsReplayReport(
        standards_change_candidate_id=standards_change_candidate_id,
        provider_metric_contract_version_id=provider_metric_contract_version_id,
        reference_library_version_id=reference_library_version_id,
        artifact_type=artifact_type,
        artifact_key=artifact_key,
        base_version=base_version,
        candidate_version=candidate_version,
        replay_version=REPLAY_VERSION,
        fixture_set_version=FIXTURE_SET_VERSION,
        sample_type=sample_type,
        sample_digest=_stable_hash(samples),
        approval_reference_digest=(
            _stable_hash(approval_reference.strip()) if approval_reference else None
        ),
        tenant_safe_sample=True,
        status=status,
        total_cases=len(results),
        changed_diagnoses=changed_diagnoses,
        changed_actions=changed_actions,
        changed_forecasts=changed_forecasts,
        changed_results=changed_results,
        newly_unknown_results=newly_unknown,
        invalidated_comparisons=invalidated,
        requires_new_baseline=requires_new_baseline,
        definition_diff_json=json.dumps(definition_diff, sort_keys=True, default=str),
        impact_report_json=json.dumps(impact_report, sort_keys=True, default=str),
        replay_results_json=json.dumps(results, sort_keys=True, default=str),
        automatic_activation_allowed=False,
        executed_by_user_id=actor_user_id,
        created_at=datetime.now(UTC),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _report_payload(row, include_detail=True)


def _validated_samples(
    sample_type: str,
    samples: list[dict[str, Any]],
    approval_reference: str | None,
    *,
    lexicon: bool = False,
) -> tuple[str, list[dict[str, Any]]]:
    resolved = sample_type.strip()
    if resolved not in SUPPORTED_SAMPLE_TYPES:
        raise StandardsReplayError("Choose fixed fixtures, approved evidence, or both.")
    if len(samples) > 200:
        raise StandardsReplayError("A replay may use at most 200 minimized evidence rows.")
    if resolved in {"approved_evidence", "combined"}:
        if not samples:
            raise StandardsReplayError("Approved evidence replay requires evidence rows.")
        if not approval_reference or not approval_reference.strip():
            raise StandardsReplayError("Approved evidence replay requires an approval reference.")
    elif samples:
        raise StandardsReplayError("Evidence rows require the approved-evidence or combined mode.")
    sanitized: list[dict[str, Any]] = []
    for sample in samples:
        if not isinstance(sample, dict):
            raise StandardsReplayError("Every evidence row must be an object.")
        allowed = (
            {"metric_id", "value"}
            if lexicon
            else {"before_value", "after_value", "before_scope_key", "after_scope_key"}
        )
        if set(sample) - allowed:
            raise StandardsReplayError(
                "Evidence rows accept only minimized measurements and comparison scope keys."
            )
        sanitized.append({key: sample.get(key) for key in sorted(allowed) if key in sample})
    return resolved, sanitized


def _contract_case_result(
    *,
    case_index: int,
    sample: dict[str, Any],
    base: ProviderMetricContractVersion,
    candidate: ProviderMetricContractVersion,
    boundary: dict[str, Any],
    source: str,
) -> dict[str, Any]:
    before = sample.get("before_value")
    after = sample.get("after_value")
    base_result = _movement_result(base.direction, base.collection_status, before, after)
    candidate_result = _movement_result(
        candidate.direction, candidate.collection_status, before, after
    )
    scope_mismatch = bool(
        sample.get("before_scope_key")
        and sample.get("after_scope_key")
        and sample.get("before_scope_key") != sample.get("after_scope_key")
    )
    comparison_valid = not boundary["required"] and not scope_mismatch
    if not comparison_valid and before is not None and after is not None:
        candidate_result = "insufficient_data"
    return {
        "case": f"{source}_{case_index}",
        "source": source,
        "base_result": base_result,
        "candidate_result": candidate_result,
        "changed": base_result != candidate_result,
        "comparison_valid": comparison_valid,
        "boundary_reasons": boundary["changed_fields"] if boundary["required"] else (
            ["scope_key"] if scope_mismatch else []
        ),
    }


def _movement_result(direction: str, status: str, before: Any, after: Any) -> str:
    if status == "not_collected" or before is None or after is None:
        return "unknown"
    try:
        before_value = float(before)
        after_value = float(after)
    except (TypeError, ValueError):
        return "unknown"
    if before_value == after_value or direction in {"neutral", "configuration"}:
        return "no_clear_change"
    improved = after_value > before_value
    if direction == "lower_is_better":
        improved = not improved
    return "improved" if improved else "declined"


def _contract_fixed_fixtures() -> list[dict[str, Any]]:
    return [
        {"before_value": 100.0, "after_value": 110.0, "before_scope_key": "same", "after_scope_key": "same"},
        {"before_value": 100.0, "after_value": 90.0, "before_scope_key": "same", "after_scope_key": "same"},
        {"before_value": 100.0, "after_value": 100.0, "before_scope_key": "same", "after_scope_key": "same"},
        {"before_value": None, "after_value": 100.0, "before_scope_key": "same", "after_scope_key": "same"},
        {"before_value": 100.0, "after_value": 110.0, "before_scope_key": "before", "after_scope_key": "after"},
    ]


def _contract_comparison_boundary(diff: dict[str, Any]) -> dict[str, Any]:
    changed = sorted(set(diff) & CONTRACT_BOUNDARY_FIELDS)
    return {
        "required": bool(changed),
        "changed_fields": changed,
        "message": (
            "Historical comparisons must start a new baseline at this version."
            if changed
            else "Saved values remain comparable when their stored scope keys also match."
        ),
    }


def _impact_report(
    db: Session,
    *,
    change_candidate_id: str | None,
    semantic_change: bool,
    comparison_boundary: dict[str, Any],
) -> dict[str, Any]:
    links = []
    if change_candidate_id:
        links = (
            db.query(StandardsImpactLink)
            .filter(StandardsImpactLink.candidate_id == change_candidate_id)
            .order_by(StandardsImpactLink.impact_type, StandardsImpactLink.impact_key)
            .all()
        )
    mapped: dict[str, list[dict[str, Any]]] = {
        "diagnoses": [],
        "actions": [],
        "forecasts": [],
        "reports": [],
        "historical_comparisons": [],
        "other": [],
    }
    type_map = {
        "lexicon_rule": "diagnoses",
        "metric_contract": "diagnoses",
        "action_contract": "actions",
        "forecast": "forecasts",
        "report": "reports",
        "historical_comparison": "historical_comparisons",
    }
    for link in links:
        target = type_map.get(link.impact_type, "other")
        changed = semantic_change and target in {"diagnoses", "actions", "forecasts"}
        if target == "historical_comparisons":
            changed = comparison_boundary["required"]
        mapped[target].append(
            {
                "key": link.impact_key,
                "impact_type": link.impact_type,
                "status": "changed" if changed else "reviewed_no_output_change",
                "reason": link.impact_reason,
            }
        )
    mapped["comparison_boundary"] = comparison_boundary
    return mapped


def _lexicon_diff(
    base: dict[str, Any], candidate: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    specs = {
        "metrics": "metric_id",
        "diagnostics": "diagnostic_id",
        "actions": "action_id",
        "policies": "policy_id",
    }
    diff: dict[str, Any] = {}
    changed_items: dict[str, list[dict[str, Any]]] = {}
    for collection, key_field in specs.items():
        base_rows = _keyed_rows(base.get(collection), key_field)
        candidate_rows = _keyed_rows(candidate.get(collection), key_field)
        keys = sorted(set(base_rows) | set(candidate_rows))
        items: list[dict[str, Any]] = []
        for key in keys:
            before = base_rows.get(key)
            after = candidate_rows.get(key)
            if before == after:
                continue
            status = "added" if before is None else "removed" if after is None else "changed"
            items.append(
                {
                    "key": key,
                    "status": status,
                    "changed_fields": sorted(_object_diff(before or {}, after or {})),
                }
            )
        diff[collection] = items
        changed_items[collection] = items
    diff["meta"] = _object_diff(base.get("meta", {}), candidate.get("meta", {}))
    return diff, changed_items


def _lexicon_fixed_fixtures(
    base: dict[str, Any],
    candidate: dict[str, Any],
    changed_items: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    base_metrics = _keyed_rows(base.get("metrics"), "metric_id")
    candidate_metrics = _keyed_rows(candidate.get("metrics"), "metric_id")
    results: list[dict[str, Any]] = []
    for item in changed_items["metrics"]:
        metric_id = item["key"]
        before = base_metrics.get(metric_id)
        after = candidate_metrics.get(metric_id)
        for index, value in enumerate(_threshold_fixture_values(before, after), start=1):
            base_result = _metric_threshold_result(before, value)
            candidate_result = _metric_threshold_result(after, value)
            results.append(
                {
                    "case": f"fixed_fixture_{metric_id}_{index}",
                    "source": "fixed_fixture",
                    "metric_id": metric_id,
                    "base_result": base_result,
                    "candidate_result": candidate_result,
                    "changed": base_result != candidate_result,
                    "comparison_valid": not _metric_boundary_fields(before, after),
                    "boundary_reasons": _metric_boundary_fields(before, after),
                }
            )
    return results


def _lexicon_evidence_result(
    index: int,
    sample: dict[str, Any],
    base: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    metric_id = str(sample.get("metric_id") or "").strip()
    value = sample.get("value")
    base_metric = _keyed_rows(base.get("metrics"), "metric_id").get(metric_id)
    candidate_metric = _keyed_rows(candidate.get("metrics"), "metric_id").get(metric_id)
    boundary_fields = _metric_boundary_fields(base_metric, candidate_metric)
    base_result = _metric_threshold_result(base_metric, value)
    candidate_result = _metric_threshold_result(candidate_metric, value)
    return {
        "case": f"approved_evidence_{index}",
        "source": "approved_evidence",
        "metric_id": metric_id,
        "base_result": base_result,
        "candidate_result": candidate_result,
        "changed": base_result != candidate_result,
        "comparison_valid": not boundary_fields,
        "boundary_reasons": boundary_fields,
    }


def _metric_threshold_result(metric: dict[str, Any] | None, value: Any) -> str:
    if not metric or value is None or not isinstance(metric.get("thresholds"), dict):
        return "unknown"
    try:
        numeric = float(value)
        thresholds = metric["thresholds"]
        good = float(thresholds["good_boundary"])
        poor = float(thresholds["poor_boundary"])
    except (KeyError, TypeError, ValueError):
        return "unknown"
    direction = thresholds.get("direction")
    if direction == "lower_is_better":
        return "good" if numeric <= good else "poor" if numeric > poor else "needs_work"
    if direction == "higher_is_better":
        return "good" if numeric >= good else "poor" if numeric < poor else "needs_work"
    return "unknown"


def _threshold_fixture_values(
    base: dict[str, Any] | None, candidate: dict[str, Any] | None
) -> list[float]:
    values: set[float] = set()
    for metric in (base, candidate):
        thresholds = metric.get("thresholds") if metric else None
        if not isinstance(thresholds, dict):
            continue
        for key in ("good_boundary", "poor_boundary"):
            try:
                boundary = float(thresholds[key])
            except (KeyError, TypeError, ValueError):
                continue
            epsilon = max(abs(boundary) * 0.001, 0.001)
            values.update({boundary - epsilon, boundary, boundary + epsilon})
    return sorted(values) or [0.0]


def _lexicon_boundary(changed_items: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    fields: list[str] = []
    for item in changed_items["metrics"]:
        if set(item["changed_fields"]) & LEXICON_BOUNDARY_FIELDS or item["status"] in {
            "added",
            "removed",
        }:
            fields.append(item["key"])
    return {
        "required": bool(fields),
        "metric_ids": sorted(fields),
        "message": (
            "Incompatible metric definitions require a new historical baseline."
            if fields
            else "Raw historical measurements remain comparable; changed thresholds retain their original version labels."
        ),
    }


def _metric_boundary_fields(
    base: dict[str, Any] | None, candidate: dict[str, Any] | None
) -> list[str]:
    if base is None or candidate is None:
        return ["metric_presence"]
    changed = _object_diff(base, candidate)
    return sorted(set(changed) & LEXICON_BOUNDARY_FIELDS)


def _reference_version(db: Session, tenant_id: str, version: str | None) -> ReferenceLibraryVersion:
    if not version:
        raise StandardsReplayError("Reference Library version is required.")
    row = (
        db.query(ReferenceLibraryVersion)
        .filter(
            ReferenceLibraryVersion.tenant_id == tenant_id,
            ReferenceLibraryVersion.version == version,
        )
        .one_or_none()
    )
    if row is None:
        raise StandardsReplayError("Reference Library version was not found.")
    return row


def _lexicon_payload(db: Session, version: ReferenceLibraryVersion) -> dict[str, Any]:
    artifact = (
        db.query(ReferenceLibraryArtifact)
        .filter(
            ReferenceLibraryArtifact.reference_library_version_id == version.id,
            ReferenceLibraryArtifact.artifact_type == "intelligence_lexicon",
        )
        .one_or_none()
    )
    if artifact is None or not artifact.payload_json:
        raise StandardsReplayError("The Reference Library version has no saved intelligence lexicon.")
    try:
        payload = json.loads(artifact.payload_json)
    except json.JSONDecodeError as exc:
        raise StandardsReplayError("The saved intelligence lexicon is invalid.") from exc
    if not isinstance(payload, dict):
        raise StandardsReplayError("The saved intelligence lexicon must be an object.")
    return payload


def _contract_definition_payload(row: ProviderMetricContractVersion) -> dict[str, Any]:
    return {
        "provider_name": row.provider_name,
        "metric_family": row.metric_family,
        "metric_id": row.metric_id,
        "display_name": row.display_name,
        "definition": row.definition,
        "unit": row.unit,
        "aggregation": row.aggregation,
        "direction": row.direction,
        "collection_status": row.collection_status,
        "authoritative_source_id": row.authoritative_source_id,
        "required_scope_fields": list(row.required_scope_fields or []),
        "optional_scope_fields": list(row.optional_scope_fields or []),
        "comparison_keys": list(row.comparison_keys or []),
        "freshness_days": row.freshness_days,
    }


def _contract_candidate_payload(row: ProviderMetricContractVersion) -> dict[str, Any]:
    return {
        "id": row.id,
        "contract_id": row.contract_id,
        "version": row.version,
        **_contract_definition_payload(row),
        "content_hash": row.content_hash,
        "is_active": row.is_active,
        "lifecycle_status": row.lifecycle_status,
        "supersedes_version_id": row.supersedes_version_id,
        "standards_change_candidate_id": row.standards_change_candidate_id,
        "proposed_by_user_id": row.proposed_by_user_id,
        "proposed_at": row.proposed_at,
        "effective_at": row.effective_at,
        "automatic_activation_allowed": False,
    }


def _normalize_contract_changes(changes: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(changes)
    for key in ("required_scope_fields", "optional_scope_fields", "comparison_keys"):
        if key in normalized:
            value = normalized[key]
            if not isinstance(value, list) or not all(
                isinstance(item, str) and item.strip() for item in value
            ):
                raise StandardsReplayError(f"{key} must be a list of field names.")
            normalized[key] = sorted(dict.fromkeys(item.strip() for item in value))
    return normalized


def _validate_contract_payload(db: Session, payload: dict[str, Any]) -> None:
    if payload["direction"] not in {
        "higher_is_better",
        "lower_is_better",
        "neutral",
        "configuration",
    }:
        raise StandardsReplayError("Unsupported metric direction.")
    if payload["collection_status"] not in {"collected", "derived", "not_collected"}:
        raise StandardsReplayError("Unsupported collection status.")
    if not isinstance(payload["freshness_days"], int) or payload["freshness_days"] < 1:
        raise StandardsReplayError("Freshness must be at least one day.")
    required = set(payload["required_scope_fields"])
    comparisons = set(payload["comparison_keys"])
    if not comparisons.issubset(required | set(payload["optional_scope_fields"])):
        raise StandardsReplayError("Comparison keys must be declared scope fields.")
    source_id = payload.get("authoritative_source_id")
    if source_id and db.get(StandardsSourceRegistry, source_id) is None:
        raise StandardsReplayError("Authoritative standards source was not found.")
    for field in ("provider_name", "metric_family", "metric_id", "display_name", "definition", "unit", "aggregation"):
        if not isinstance(payload.get(field), str) or not payload[field].strip():
            raise StandardsReplayError(f"{field} is required.")


def _keyed_rows(value: Any, key_field: str) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list):
        return {}
    return {
        str(row[key_field]): row
        for row in value
        if isinstance(row, dict) and row.get(key_field)
    }


def _object_diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    return {
        key: {"before": before.get(key), "after": after.get(key)}
        for key in sorted(set(before) | set(after))
        if before.get(key) != after.get(key)
    }


def _changed_surface_count(items: Any) -> int:
    if not isinstance(items, list):
        return 0
    return sum(
        isinstance(item, dict) and item.get("status") in {"changed", "added", "removed"}
        for item in items
    )


def _report_payload(row: StandardsReplayReport, *, include_detail: bool) -> dict[str, Any]:
    payload = {
        "id": row.id,
        "standards_change_candidate_id": row.standards_change_candidate_id,
        "artifact_type": row.artifact_type,
        "artifact_key": row.artifact_key,
        "base_version": row.base_version,
        "candidate_version": row.candidate_version,
        "replay_version": row.replay_version,
        "fixture_set_version": row.fixture_set_version,
        "sample_type": row.sample_type,
        "sample_digest": row.sample_digest,
        "tenant_safe_sample": row.tenant_safe_sample,
        "status": row.status,
        "total_cases": row.total_cases,
        "changed_diagnoses": row.changed_diagnoses,
        "changed_actions": row.changed_actions,
        "changed_forecasts": row.changed_forecasts,
        "changed_results": row.changed_results,
        "newly_unknown_results": row.newly_unknown_results,
        "invalidated_comparisons": row.invalidated_comparisons,
        "requires_new_baseline": row.requires_new_baseline,
        "automatic_activation_allowed": False,
        "executed_by_user_id": row.executed_by_user_id,
        "created_at": row.created_at,
    }
    if include_detail:
        payload["definition_diff"] = _json_object(row.definition_diff_json)
        payload["impact_report"] = _json_object(row.impact_report_json)
        payload["replay_results"] = _json_list(row.replay_results_json)
    return payload


def _json_object(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_list(value: str) -> list[Any]:
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


def _stable_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(encoded.encode("utf-8")).hexdigest()
