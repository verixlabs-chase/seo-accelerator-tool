from __future__ import annotations

from datetime import UTC, datetime, timedelta
from functools import lru_cache
from random import randint, uniform
from typing import Protocol

from app.core.config import get_settings


class LocalProvider(Protocol):
    def bootstrap_profile(self, campaign_id: str) -> dict:
        ...

    def fetch_profile_snapshot(self, campaign_id: str) -> dict:
        ...

    def fetch_reviews(self, campaign_id: str, limit: int = 5) -> list[dict]:
        ...


class SyntheticLocalProvider:
    def bootstrap_profile(self, campaign_id: str) -> dict:  # noqa: ARG002
        return {
            "provider": "gbp",
            "profile_name": "Primary GBP Profile",
            "map_pack_position": randint(1, 20),
        }

    def fetch_profile_snapshot(self, campaign_id: str) -> dict:  # noqa: ARG002
        return {"map_pack_position": randint(1, 20)}

    def fetch_reviews(self, campaign_id: str, limit: int = 5) -> list[dict]:
        now = datetime.now(UTC)
        rows: list[dict] = []
        for i in range(max(1, limit)):
            rating = round(uniform(3.0, 5.0), 1)
            rows.append(
                {
                    "external_review_id": f"{campaign_id}-r-{i}",
                    "rating": rating,
                    "sentiment": "positive" if rating >= 4.0 else "neutral",
                    "body": f"Sample review {i}",
                    "reviewed_at": now - timedelta(days=i * 2),
                }
            )
        return rows


@lru_cache
def get_local_provider() -> LocalProvider:
    settings = get_settings()
    backend = getattr(settings, "local_provider_backend", "synthetic").strip().lower()
    if backend == "synthetic":
        return SyntheticLocalProvider()
    raise ValueError(f"Unsupported local provider backend: {backend}")
