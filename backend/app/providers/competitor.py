from __future__ import annotations

from hashlib import sha256
from typing import Protocol

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.competitor import CompetitorPage, CompetitorRanking, CompetitorSignal


class CompetitorProvider(Protocol):
    def collect_competitor_snapshot(
        self,
        *,
        db: Session,
        tenant_id: str,
        campaign_id: str,
        competitor_id: str,
        domain: str,
    ) -> dict | None:
        ...


class FixtureCompetitorProvider:
    @staticmethod
    def _stable_int(seed: str, minimum: int, maximum: int) -> int:
        span = max(1, maximum - minimum + 1)
        digest = sha256(seed.encode("utf-8")).digest()
        return minimum + (int.from_bytes(digest[:8], "big") % span)

    @staticmethod
    def _stable_float(seed: str, minimum: float, maximum: float, decimals: int = 2) -> float:
        digest = sha256(seed.encode("utf-8")).digest()
        scaled = int.from_bytes(digest[8:16], "big") / float(2**64)
        return round(minimum + ((maximum - minimum) * scaled), decimals)

    def collect_competitor_snapshot(
        self,
        *,
        db: Session,  # noqa: ARG002
        tenant_id: str,  # noqa: ARG002
        campaign_id: str,
        competitor_id: str,  # noqa: ARG002
        domain: str,
    ) -> dict | None:
        seed = f"{campaign_id}|{domain.lower().strip()}"
        return {
            "keyword": "best local seo agency",
            "position": self._stable_int(f"{seed}:position", 1, 100),
            "url": f"https://{domain}/services",
            "visibility_score": self._stable_float(f"{seed}:visibility", 0.1, 1.0),
            "signal_key": "content_velocity",
            "signal_value": "weekly",
            "signal_score": self._stable_float(f"{seed}:signal", 0.1, 1.0),
            "confidence": 0.75,
            "source": "fixture",
        }


class StoredDatasetCompetitorProvider:
    def collect_competitor_snapshot(
        self,
        *,
        db: Session,
        tenant_id: str,
        campaign_id: str,
        competitor_id: str,
        domain: str,  # noqa: ARG002
    ) -> dict | None:
        ranking = (
            db.query(CompetitorRanking)
            .filter(
                CompetitorRanking.tenant_id == tenant_id,
                CompetitorRanking.campaign_id == campaign_id,
                CompetitorRanking.competitor_id == competitor_id,
            )
            .order_by(CompetitorRanking.captured_at.desc())
            .first()
        )
        page = (
            db.query(CompetitorPage)
            .filter(
                CompetitorPage.tenant_id == tenant_id,
                CompetitorPage.campaign_id == campaign_id,
                CompetitorPage.competitor_id == competitor_id,
            )
            .order_by(CompetitorPage.captured_at.desc())
            .first()
        )
        signal = (
            db.query(CompetitorSignal)
            .filter(
                CompetitorSignal.tenant_id == tenant_id,
                CompetitorSignal.campaign_id == campaign_id,
                CompetitorSignal.competitor_id == competitor_id,
            )
            .order_by(CompetitorSignal.captured_at.desc())
            .first()
        )
        if ranking is None or page is None or signal is None:
            return None
        return {
            "keyword": ranking.keyword,
            "position": int(ranking.position),
            "url": page.url,
            "visibility_score": float(page.visibility_score),
            "signal_key": signal.signal_key,
            "signal_value": signal.signal_value,
            "signal_score": float(signal.score),
            "confidence": 0.9,
            "source": "dataset",
        }


def get_competitor_provider_for_organization(db: Session, organization_id: str) -> CompetitorProvider:  # noqa: ARG001
    settings = get_settings()
    backend = getattr(settings, "competitor_provider_backend", "dataset").strip().lower()
    if backend == "dataset":
        return StoredDatasetCompetitorProvider()
    if backend in {"fixture", "synthetic"}:
        if getattr(settings, "app_env", "").strip().lower() != "test":
            raise ValueError("competitor_provider_unavailable: fixture backend is allowed only in test mode.")
        return FixtureCompetitorProvider()
    raise ValueError(f"Unsupported competitor provider backend: {backend}")
