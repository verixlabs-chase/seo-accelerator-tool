from __future__ import annotations

import argparse
import importlib
import json
import locale
import os
from pathlib import Path
import random
import sys
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from app.governance.replay.schema import ReplayCase, ReplayReport

_VOLATILE_KEYS = {
    "generated_at",
    "request_id",
    "trace_id",
    "created_at",
    "updated_at",
    "detected_at",
}


ExecutorAdapter = Callable[["ReplayCase"], dict[str, Any]]


def _bootstrap_script_path() -> None:
    # Allow direct script execution from backend/scripts/replay.
    # Module execution (python -m scripts.replay.run_replay) does not require this.
    root = Path(__file__).resolve().parents[2]
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)


def _load_replay_dependencies() -> tuple[Any, Any, Any, Any, Any, Any, Any]:
    comparator = importlib.import_module("app.governance.replay.comparator")
    schema = importlib.import_module("app.governance.replay.schema")
    return (
        comparator.compare_confidence_bands,
        comparator.compare_hashes,
        comparator.compare_ordering,
        comparator.diff_payload,
        schema.DriftEvent,
        schema.ReplayCase,
        schema.ReplayReport,
    )


def _lock_deterministic_environment() -> None:
    os.environ["TZ"] = "UTC"
    if hasattr(__import__("time"), "tzset"):
        __import__("time").tzset()
    try:
        locale.setlocale(locale.LC_ALL, "C.UTF-8")
    except locale.Error:
        locale.setlocale(locale.LC_ALL, "C")
    random.seed(0)
    os.environ.setdefault("PYTHONHASHSEED", "0")


def _load_manifest(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _load_executor(executor_ref: str | None) -> ExecutorAdapter:
    if not executor_ref:
        raise RuntimeError("Replay executor must be configured via --executor module:function")
    if ":" not in executor_ref:
        raise RuntimeError("Executor reference must be in module:function format")
    module_name, func_name = executor_ref.split(":", 1)
    module = importlib.import_module(module_name)
    candidate = getattr(module, func_name, None)
    if candidate is None or not callable(candidate):
        raise RuntimeError(f"Replay executor callable not found: {executor_ref}")
    return candidate


def _strip_volatile_fields(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: _strip_volatile_fields(value)
            for key, value in payload.items()
            if key not in _VOLATILE_KEYS
        }
    if isinstance(payload, list):
        return [_strip_volatile_fields(item) for item in payload]
    return payload


def _ordering_signature(payload: dict[str, Any]) -> list[dict[str, Any]]:
    recs = payload.get("recommendations", [])
    if not isinstance(recs, list):
        return []
    signature: list[dict[str, Any]] = []
    for idx, rec in enumerate(recs):
        if not isinstance(rec, dict):
            continue
        signature.append(
            {
                "index": idx,
                "scenario_id": rec.get("scenario_id"),
                "priority_score": rec.get("priority_score"),
                "impact_level": rec.get("impact_level"),
                "confidence_band": _band(float(rec.get("confidence", 0.0))),
            }
        )
    return signature


def _band(value: float) -> str:
    if value >= 0.8:
        return "high"
    if value >= 0.6:
        return "medium"
    return "low"


def _validate_corpus(manifest_path: Path, manifest: dict[str, Any]) -> None:
    if not manifest_path.exists():
        raise FileNotFoundError(f"Replay corpus manifest missing: {manifest_path}")

    cases = manifest.get("cases", [])
    if not isinstance(cases, list) or len(cases) == 0:
        raise RuntimeError("Replay corpus must include at least one case")

    case_dir = manifest_path.parent
    for item in cases:
        input_ref = case_dir / item["input_ref"]
        expected_ref = case_dir / item["expected_ref"]
        if not input_ref.exists():
            raise FileNotFoundError(f"Replay case input missing: {input_ref}")
        if not expected_ref.exists():
            raise FileNotFoundError(f"Replay case expected output missing: {expected_ref}")


def run_replay(manifest_path: Path, *, executor: ExecutorAdapter) -> "ReplayReport":
    _lock_deterministic_environment()
    (
        compare_confidence_bands,
        compare_hashes,
        compare_ordering,
        diff_payload,
        DriftEvent,
        ReplayCase,
        ReplayReport,
    ) = _load_replay_dependencies()

    manifest = _load_manifest(manifest_path)
    _validate_corpus(manifest_path, manifest)

    corpus_version = str(manifest.get("corpus_version", "unknown"))
    cases = manifest.get("cases", [])
    drift_events: list[Any] = []

    for item in cases:
        case_dir = manifest_path.parent
        input_payload = _load_json(case_dir / item["input_ref"])
        expected_output = _load_json(case_dir / item["expected_ref"])
        case = ReplayCase(
            case_id=item["case_id"],
            tenant_id=item["tenant_id"],
            campaign_id=item["campaign_id"],
            input_payload=input_payload,
            expected_output=expected_output,
            version_tuple=item["version_tuple"],
        )
        actual_output = executor(case)

        expected_sanitized = _strip_volatile_fields(case.expected_output)
        actual_sanitized = _strip_volatile_fields(actual_output)

        match_hash, expected_hash, actual_hash = compare_hashes(expected_sanitized, actual_sanitized)
        if not match_hash:
            drift_events.append(
                DriftEvent(
                    case_id=case.case_id,
                    tenant_id=case.tenant_id,
                    campaign_id=case.campaign_id,
                    drift_type="hash",
                    expected=expected_hash,
                    actual=actual_hash,
                    diff=diff_payload(expected_sanitized, actual_sanitized),
                )
            )

        match_order, expected_order, actual_order = compare_ordering(expected_sanitized, actual_sanitized)
        if not match_order:
            drift_events.append(
                DriftEvent(
                    case_id=case.case_id,
                    tenant_id=case.tenant_id,
                    campaign_id=case.campaign_id,
                    drift_type="ordering",
                    expected=expected_order,
                    actual=actual_order,
                )
            )

        expected_signature = _ordering_signature(expected_sanitized)
        actual_signature = _ordering_signature(actual_sanitized)
        if expected_signature != actual_signature:
            drift_events.append(
                DriftEvent(
                    case_id=case.case_id,
                    tenant_id=case.tenant_id,
                    campaign_id=case.campaign_id,
                    drift_type="ordering",
                    expected=json.dumps(expected_signature, sort_keys=True),
                    actual=json.dumps(actual_signature, sort_keys=True),
                )
            )

        match_bands, expected_bands, actual_bands = compare_confidence_bands(expected_sanitized, actual_sanitized)
        if not match_bands:
            drift_events.append(
                DriftEvent(
                    case_id=case.case_id,
                    tenant_id=case.tenant_id,
                    campaign_id=case.campaign_id,
                    drift_type="confidence_band",
                    expected=expected_bands,
                    actual=actual_bands,
                )
            )

    total_cases = len(cases)
    failed_case_ids = {event.case_id for event in drift_events}
    failed_cases = len(failed_case_ids)
    passed_cases = total_cases - failed_cases

    return ReplayReport(
        corpus_version=corpus_version,
        total_cases=total_cases,
        passed_cases=passed_cases,
        failed_cases=failed_cases,
        drift_events=drift_events,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic replay against a corpus manifest.")
    parser.add_argument("--manifest", required=True, help="Path to replay manifest.json")
    parser.add_argument("--report", required=True, help="Path to output replay report JSON")
    parser.add_argument("--executor", required=True, help="Executor adapter module:function")
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve()
    report_path = Path(args.report).resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        executor = _load_executor(args.executor)
        report = run_replay(manifest_path, executor=executor)
    except Exception as exc:
        error_report = {
            "corpus_version": "unknown",
            "total_cases": 0,
            "passed_cases": 0,
            "failed_cases": 1,
            "drift_events": [
                {
                    "case_id": "_bootstrap_",
                    "tenant_id": "_bootstrap_",
                    "campaign_id": "_bootstrap_",
                    "drift_type": "payload",
                    "expected": "valid_replay_corpus",
                    "actual": str(exc),
                    "diff": None,
                }
            ],
        }
        report_path.write_text(json.dumps(error_report, indent=2), encoding="utf-8")
        return 1

    report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return 1 if report.failed_cases > 0 else 0


if __name__ == "__main__":
    _bootstrap_script_path()
    raise SystemExit(main())
