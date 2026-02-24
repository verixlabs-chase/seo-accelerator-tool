from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.governance.replay.hashing import output_hash

# Usage:
#   python scripts/replay/build_golden.py --corpus app/testing/fixtures/replay_corpus/v1 --output artifacts/replay/baseline/v1


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, sort_keys=True)


def build_golden(corpus_root: Path, output_root: Path) -> dict[str, Any]:
    manifest_path = corpus_root / "manifest.json"
    manifest = _load_json(manifest_path)
    cases = manifest.get("cases", [])

    report_cases: list[dict[str, Any]] = []
    for case in cases:
        expected_payload = _load_json(corpus_root / case["expected_ref"])
        digest = output_hash(expected_payload)
        report_cases.append({"case_id": case["case_id"], "output_hash": digest})

    report = {
        "corpus_version": manifest.get("corpus_version", "unknown"),
        "case_count": len(cases),
        "cases": report_cases,
    }
    _write_json(output_root / "manifest.json", report)
    return report


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
    raise SystemExit(main())
