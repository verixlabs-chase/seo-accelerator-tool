from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from sqlalchemy.orm import Session

from app.intelligence.lexicon.schema import IntelligenceLexicon
from app.models.reference_library import ReferenceLibraryArtifact, ReferenceLibraryVersion
from app.reference_library.paths import reference_library_file


LEXICON_ARTIFACT_TYPE = "intelligence_lexicon"
BUILTIN_LEXICON_PATH = ("intelligence", "seo_intelligence_v1.json")


def load_lexicon_payload(payload: dict[str, Any]) -> IntelligenceLexicon:
    return IntelligenceLexicon.model_validate(payload)


@lru_cache(maxsize=1)
def get_builtin_lexicon() -> IntelligenceLexicon:
    path = reference_library_file(*BUILTIN_LEXICON_PATH)
    return load_lexicon_payload(json.loads(path.read_text(encoding="utf-8")))


def get_active_lexicon(
    db: Session | None,
    *,
    tenant_id: str | None = None,
) -> IntelligenceLexicon:
    if db is None or not tenant_id:
        return get_builtin_lexicon()

    active_version = (
        db.query(ReferenceLibraryVersion)
        .filter(
            ReferenceLibraryVersion.tenant_id == tenant_id,
            ReferenceLibraryVersion.status == "active",
        )
        .order_by(ReferenceLibraryVersion.updated_at.desc())
        .first()
    )
    if active_version is None:
        return get_builtin_lexicon()

    artifact = (
        db.query(ReferenceLibraryArtifact)
        .filter(
            ReferenceLibraryArtifact.tenant_id == tenant_id,
            ReferenceLibraryArtifact.reference_library_version_id == active_version.id,
            ReferenceLibraryArtifact.artifact_type == LEXICON_ARTIFACT_TYPE,
        )
        .first()
    )
    if artifact is None or not artifact.payload_json:
        return get_builtin_lexicon()

    try:
        payload = json.loads(artifact.payload_json)
        return load_lexicon_payload(payload)
    except (TypeError, ValueError, json.JSONDecodeError):
        # An invalid active artifact must never destabilize campaign execution.
        # Activation validation should prevent this path; the built-in pack is
        # the deterministic last-known-good fallback.
        return get_builtin_lexicon()


def clear_builtin_lexicon_cache() -> None:
    get_builtin_lexicon.cache_clear()
