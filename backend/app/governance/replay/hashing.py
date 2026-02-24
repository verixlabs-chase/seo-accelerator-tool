from __future__ import annotations

import hashlib
import json
from typing import Any

from app.governance.replay.canonicalize import canonicalize_payload


def _to_canonical_json(payload: Any) -> str:
    canonical = canonicalize_payload(payload)
    return json.dumps(canonical, separators=(",", ":"), sort_keys=True, ensure_ascii=True)


def version_fingerprint(version_tuple: dict[str, str]) -> str:
    return hashlib.sha256(_to_canonical_json(version_tuple).encode("utf-8")).hexdigest()


def input_hash(payload: Any) -> str:
    return hashlib.sha256(_to_canonical_json(payload).encode("utf-8")).hexdigest()


def output_hash(payload: Any) -> str:
    return hashlib.sha256(_to_canonical_json(payload).encode("utf-8")).hexdigest()


def build_hash(*, input_digest: str, output_digest: str, version_digest: str) -> str:
    material = f"{input_digest}|{output_digest}|{version_digest}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()
