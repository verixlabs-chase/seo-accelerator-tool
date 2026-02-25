from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from typing import Any


def _bootstrap_script_path() -> None:
    root = Path(__file__).resolve().parents[2]
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, sort_keys=True)


def _confidence_band(value: float) -> str:
    if value >= 0.8:
        return "high"
    if value >= 0.6:
        return "medium"
    return "low"


def _ordering(payload: dict[str, Any]) -> list[str]:
    recommendations = payload.get("recommendations", [])
    if not isinstance(recommendations, list):
        return []
    return [item.get("scenario_id") for item in recommendations if isinstance(item, dict) and isinstance(item.get("scenario_id"), str)]


def _confidence_bands(payload: dict[str, Any]) -> list[str]:
    recommendations = payload.get("recommendations", [])
    if not isinstance(recommendations, list):
        return []
    bands: list[str] = []
    for item in recommendations:
        if isinstance(item, dict) and isinstance(item.get("confidence"), (int, float)):
            bands.append(_confidence_band(float(item["confidence"])))
    return bands


def _validate_manifest(corpus_root: Path) -> dict[str, Any]:
    manifest_path = corpus_root / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Replay corpus manifest missing: {manifest_path}")
    manifest = _load_json(manifest_path)
    cases = manifest.get("cases", [])
    if not isinstance(cases, list) or len(cases) == 0:
        raise ValueError("Replay corpus manifest has no cases")
    for case in cases:
        input_ref = corpus_root / case["input_ref"]
        expected_ref = corpus_root / case["expected_ref"]
        if not input_ref.exists():
            raise FileNotFoundError(f"Replay corpus input missing: {input_ref}")
        if not expected_ref.exists():
            raise FileNotFoundError(f"Replay corpus expected output missing: {expected_ref}")
    return manifest


def build_golden(corpus_root: Path, output_root: Path) -> dict[str, Any]:
    from app.governance.replay.hashing import build_hash, input_hash, output_hash, version_fingerprint

    manifest = _validate_manifest(corpus_root)
    cases = manifest["cases"]

    result_manifest_cases: list[dict[str, Any]] = []
    case_results_dir = output_root / "case_results"
    case_results_dir.mkdir(parents=True, exist_ok=True)

    for case in cases:
        case_id = case["case_id"]
        input_payload = _load_json(corpus_root / case["input_ref"])
        expected_payload = _load_json(corpus_root / case["expected_ref"])
        version_tuple = case["version_tuple"]

        input_digest = input_hash(input_payload)
        output_digest = output_hash(expected_payload)
        version_digest = version_fingerprint(version_tuple)
        build_digest = build_hash(input_digest=input_digest, output_digest=output_digest, version_digest=version_digest)

        case_result = {
            "case_id": case_id,
            "tenant_id": case["tenant_id"],
            "campaign_id": case["campaign_id"],
            "version_tuple": version_tuple,
            "version_fingerprint": version_digest,
            "input_hash": input_digest,
            "output_hash": output_digest,
            "build_hash": build_digest,
            "recommendation_ordering": _ordering(expected_payload),
            "confidence_bands": _confidence_bands(expected_payload),
            "expected_ref": case["expected_ref"],
            "input_ref": case["input_ref"],
        }
        _write_json(case_results_dir / f"{case_id}.json", case_result)

        result_manifest_cases.append(
            {
                "case_id": case_id,
                "case_result_ref": f"case_results/{case_id}.json",
                "input_hash": input_digest,
                "output_hash": output_digest,
                "build_hash": build_digest,
            }
        )

    result_manifest = {
        "corpus_version": str(manifest.get("corpus_version", "unknown")),
        "generated_at": datetime.now(UTC).isoformat(),
        "case_count": len(cases),
        "cases": result_manifest_cases,
    }
    _write_json(output_root / "manifest.json", result_manifest)
    return result_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Build golden replay hash artifacts.")
    parser.add_argument("--corpus", required=True, help="Replay corpus root containing manifest.json")
    parser.add_argument("--output", required=True, help="Golden artifact output directory")
    args = parser.parse_args()

    corpus_root = Path(args.corpus).resolve()
    output_root = Path(args.output).resolve()
    build_golden(corpus_root=corpus_root, output_root=output_root)
    return 0


if __name__ == "__main__":
    _bootstrap_script_path()
    raise SystemExit(main())
