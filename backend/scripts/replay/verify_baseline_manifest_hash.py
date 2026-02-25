from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify replay baseline manifest integrity.")
    parser.add_argument("--manifest", required=True, help="Path to baseline manifest.json")
    parser.add_argument("--expected-sha256", required=True, help="Expected SHA-256 hex digest")
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve()
    if not manifest_path.exists():
        raise FileNotFoundError(f"Baseline manifest missing: {manifest_path}")

    actual_sha256 = file_sha256(manifest_path)
    expected_sha256 = args.expected_sha256.strip().lower()

    if actual_sha256 != expected_sha256:
        print("Baseline manifest integrity check failed.")
        print(f"Expected: {expected_sha256}")
        print(f"Actual:   {actual_sha256}")
        return 1

    print(f"Baseline manifest integrity verified: {actual_sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
