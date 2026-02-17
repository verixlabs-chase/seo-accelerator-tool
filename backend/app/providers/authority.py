from __future__ import annotations

from datetime import UTC, datetime
from functools import lru_cache
from random import uniform
from typing import Protocol

from app.core.config import get_settings


class AuthorityProvider(Protocol):
    def fetch_backlinks(self, campaign_id: str) -> list[dict]:
        ...

    def refresh_citation_status(self, campaign_id: str, directory_name: str, current_status: str) -> dict:
        ...


class SyntheticAuthorityProvider:
    def fetch_backlinks(self, campaign_id: str) -> list[dict]:
        return [
            {
                "source_url": "https://example-partner.com/local-seo-resource",
                "target_url": f"https://{campaign_id}.example.com/",
                "quality_score": round(uniform(0.5, 0.95), 2),
                "status": "live",
            }
        ]

    def refresh_citation_status(self, campaign_id: str, directory_name: str, current_status: str) -> dict:  # noqa: ARG002
        if current_status != "submitted":
            return {"submission_status": current_status, "listing_url": None, "updated_at": datetime.now(UTC)}
        return {
            "submission_status": "verified",
            "listing_url": f"https://directory.example/{directory_name.lower().replace(' ', '-')}",
            "updated_at": datetime.now(UTC),
        }


@lru_cache
def get_authority_provider() -> AuthorityProvider:
    settings = get_settings()
    backend = getattr(settings, "authority_provider_backend", "synthetic").strip().lower()
    if backend == "synthetic":
        return SyntheticAuthorityProvider()
    raise ValueError(f"Unsupported authority provider backend: {backend}")
