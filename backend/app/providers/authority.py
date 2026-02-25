from __future__ import annotations

from datetime import UTC, datetime
from functools import lru_cache
from hashlib import sha256
from typing import Protocol

from app.core.config import get_settings


class AuthorityProvider(Protocol):
    def fetch_backlinks(self, campaign_id: str) -> list[dict]:
        ...

    def refresh_citation_status(self, campaign_id: str, directory_name: str, current_status: str) -> dict:
        ...


class SyntheticAuthorityProvider:
    @staticmethod
    def _stable_float(seed: str, minimum: float, maximum: float, decimals: int = 2) -> float:
        digest = sha256(seed.encode("utf-8")).digest()
        scaled = int.from_bytes(digest[:8], "big") / float(2**64)
        return round(minimum + ((maximum - minimum) * scaled), decimals)

    def fetch_backlinks(self, campaign_id: str) -> list[dict]:
        return [
            {
                "source_url": "https://example-partner.com/local-seo-resource",
                "target_url": f"https://{campaign_id}.example.com/",
                "quality_score": self._stable_float(f"{campaign_id}:backlink", 0.5, 0.95),
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
        if getattr(settings, "app_env", "").strip().lower() != "test":
            raise ValueError("authority_provider_unavailable: synthetic backend is allowed only in test fixture mode.")
        return SyntheticAuthorityProvider()
    raise ValueError(f"Unsupported authority provider backend: {backend}")
