from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.intelligence.lexicon.schema import IntelligenceLexicon
from app.models.reference_library import ReferenceLibraryStandardsCheck


CRUX_QUERY_ENDPOINT = "https://chromeuxreport.googleapis.com/v1/records:queryRecord"
CRUX_SOURCE_ID = "chrome.crux.api"
CRUX_METRIC_KEYS = {
    "cwv.lcp": "largest_contentful_paint",
    "cwv.inp": "interaction_to_next_paint",
    "cwv.cls": "cumulative_layout_shift",
}


def fetch_crux_standard_probe(
    *,
    api_key: str,
    origin: str,
    timeout_seconds: float = 15.0,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    if not api_key.strip():
        raise ValueError("CRUX_API_KEY is required to check current standards")
    if not origin.startswith("https://"):
        raise ValueError("Core Web Vitals standards probe origin must use https://")

    owns_client = client is None
    resolved_client = client or httpx.Client(timeout=timeout_seconds)
    try:
        response = resolved_client.post(
            CRUX_QUERY_ENDPOINT,
            params={"key": api_key},
            json={
                "origin": origin,
                "metrics": list(CRUX_METRIC_KEYS.values()),
            },
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("CrUX standards probe returned a non-object payload")
        return payload
    finally:
        if owns_client:
            resolved_client.close()


def extract_crux_thresholds(payload: dict[str, Any]) -> dict[str, dict[str, float]]:
    record = payload.get("record")
    metrics = record.get("metrics") if isinstance(record, dict) else None
    if not isinstance(metrics, dict):
        raise ValueError("CrUX response does not contain record.metrics")

    normalized: dict[str, dict[str, float]] = {}
    for metric_id, provider_key in CRUX_METRIC_KEYS.items():
        provider_metric = metrics.get(provider_key)
        if not isinstance(provider_metric, dict):
            continue
        histogram = provider_metric.get("histogram")
        if not isinstance(histogram, list) or len(histogram) < 3:
            continue
        good_bin = histogram[0] if isinstance(histogram[0], dict) else {}
        needs_bin = histogram[1] if isinstance(histogram[1], dict) else {}
        if good_bin.get("end") is None or needs_bin.get("end") is None:
            continue
        normalized[metric_id] = {
            "good_boundary": float(good_bin["end"]),
            "poor_boundary": float(needs_bin["end"]),
        }
    return normalized


def compare_crux_thresholds(
    lexicon: IntelligenceLexicon,
    observed: dict[str, dict[str, float]],
) -> dict[str, Any]:
    drift: list[dict[str, Any]] = []
    missing: list[str] = []
    for metric_id in sorted(CRUX_METRIC_KEYS):
        metric = lexicon.metric_index[metric_id]
        thresholds = metric.thresholds
        observed_thresholds = observed.get(metric_id)
        if thresholds is None:
            drift.append(
                {
                    "metric_id": metric_id,
                    "field": "thresholds",
                    "active": None,
                    "observed": observed_thresholds,
                    "reason": "active_metric_has_no_thresholds",
                }
            )
            continue
        if observed_thresholds is None:
            missing.append(metric_id)
            continue
        for field in ("good_boundary", "poor_boundary"):
            active_value = float(getattr(thresholds, field))
            observed_value = float(observed_thresholds[field])
            tolerance = 0.0001 if metric.unit == "score" else 0.01
            if abs(active_value - observed_value) > tolerance:
                drift.append(
                    {
                        "metric_id": metric_id,
                        "field": field,
                        "active": active_value,
                        "observed": observed_value,
                        "reason": "official_crux_histogram_boundary_changed",
                    }
                )

    status = "current"
    if missing:
        status = "incomplete"
    if drift:
        status = "review_required"
    return {
        "status": status,
        "lexicon_version": lexicon.meta.version,
        "observed_thresholds": observed,
        "missing_metric_ids": missing,
        "drift": drift,
        "automatic_activation_allowed": False,
        "next_step": (
            "No standards change detected."
            if status == "current"
            else "Review official sources, update the lexicon, validate replay parity, and activate a new version."
        ),
    }


def run_and_record_crux_standards_check(
    db: Session,
    *,
    lexicon: IntelligenceLexicon,
    api_key: str,
    origin: str,
    timeout_seconds: float = 15.0,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    raw_payload = fetch_crux_standard_probe(
        api_key=api_key,
        origin=origin,
        timeout_seconds=timeout_seconds,
        client=client,
    )
    observed = extract_crux_thresholds(raw_payload)
    comparison = compare_crux_thresholds(lexicon, observed)
    packed_source = json.dumps(raw_payload, sort_keys=True, separators=(",", ":"))
    row = ReferenceLibraryStandardsCheck(
        source_id=CRUX_SOURCE_ID,
        source_uri=CRUX_QUERY_ENDPOINT,
        lexicon_version=lexicon.meta.version,
        status=str(comparison["status"]),
        source_digest=hashlib.sha256(packed_source.encode("utf-8")).hexdigest(),
        normalized_payload_json=json.dumps(observed, sort_keys=True),
        drift_json=json.dumps(comparison["drift"], sort_keys=True),
        observed_at=datetime.now(UTC),
    )
    db.add(row)
    db.commit()
    return {
        **comparison,
        "check_id": row.id,
        "source_id": row.source_id,
        "source_uri": row.source_uri,
        "observed_at": row.observed_at,
    }


def latest_crux_standards_check(db: Session) -> dict[str, Any] | None:
    row = (
        db.query(ReferenceLibraryStandardsCheck)
        .filter(ReferenceLibraryStandardsCheck.source_id == CRUX_SOURCE_ID)
        .order_by(
            ReferenceLibraryStandardsCheck.observed_at.desc(),
            ReferenceLibraryStandardsCheck.id.desc(),
        )
        .first()
    )
    if row is None:
        return None
    return {
        "check_id": row.id,
        "source_id": row.source_id,
        "source_uri": row.source_uri,
        "lexicon_version": row.lexicon_version,
        "status": row.status,
        "observed_thresholds": _json_object(row.normalized_payload_json),
        "drift": _json_list(row.drift_json),
        "observed_at": row.observed_at,
        "automatic_activation_allowed": False,
    }


def _json_object(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_list(raw: str) -> list[Any]:
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []
