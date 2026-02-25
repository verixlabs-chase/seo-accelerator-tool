from __future__ import annotations

from datetime import UTC, datetime, timedelta
from functools import lru_cache
from hashlib import sha256
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
    @staticmethod
    def _stable_int(seed: str, minimum: int, maximum: int) -> int:
        span = max(1, maximum - minimum + 1)
        digest = sha256(seed.encode("utf-8")).digest()
        return minimum + (int.from_bytes(digest[:8], "big") % span)

    @staticmethod
    def _stable_float(seed: str, minimum: float, maximum: float, decimals: int = 1) -> float:
        digest = sha256(seed.encode("utf-8")).digest()
        scaled = int.from_bytes(digest[8:16], "big") / float(2**64)
        return round(minimum + ((maximum - minimum) * scaled), decimals)

    def bootstrap_profile(self, campaign_id: str) -> dict:  # noqa: ARG002
        return {
            "provider": "gbp",
            "profile_name": "Primary GBP Profile",
            "map_pack_position": self._stable_int(f"{campaign_id}:bootstrap", 1, 20),
        }

    def fetch_profile_snapshot(self, campaign_id: str) -> dict:  # noqa: ARG002
        return {"map_pack_position": self._stable_int(f"{campaign_id}:snapshot", 1, 20)}

    def fetch_reviews(self, campaign_id: str, limit: int = 5) -> list[dict]:
        now = datetime.now(UTC)
        rows: list[dict] = []
        for i in range(max(1, limit)):
            rating = self._stable_float(f"{campaign_id}:review:{i}", 3.0, 5.0, decimals=1)
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
        if getattr(settings, "app_env", "").strip().lower() != "test":
            raise ValueError("local_provider_unavailable: synthetic backend is allowed only in test fixture mode.")
        return SyntheticLocalProvider()
    raise ValueError(f"Unsupported local provider backend: {backend}")
