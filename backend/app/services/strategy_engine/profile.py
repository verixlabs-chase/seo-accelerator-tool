from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.governance.replay.hashing import version_fingerprint


class StrategyEngineProfile(BaseModel):
    model_config = ConfigDict(extra='forbid')

    profile_name: str
    momentum_weight: float = Field(ge=0.0, le=2.0)
    volatility_penalty_weight: float = Field(ge=0.0, le=2.0)
    trend_window_days: int = Field(ge=7, le=365)
    confidence_decay_curve: list[float] = Field(default_factory=list)

    def version_hash(self) -> str:
        payload = {
            'profile_name': self.profile_name,
            'momentum_weight': round(self.momentum_weight, 6),
            'volatility_penalty_weight': round(self.volatility_penalty_weight, 6),
            'trend_window_days': self.trend_window_days,
            'confidence_decay_curve': [round(item, 6) for item in self.confidence_decay_curve],
        }
        return version_fingerprint(payload)


def resolve_strategy_profile(tier: str) -> StrategyEngineProfile:
    normalized = tier.strip().lower()
    if normalized == 'enterprise':
        return StrategyEngineProfile(
            profile_name='enterprise_temporal_v1',
            momentum_weight=0.18,
            volatility_penalty_weight=0.12,
            trend_window_days=60,
            confidence_decay_curve=[1.0, 0.88, 0.72],
        )
    return StrategyEngineProfile(
        profile_name='pro_temporal_v1',
        momentum_weight=0.14,
        volatility_penalty_weight=0.10,
        trend_window_days=45,
        confidence_decay_curve=[1.0, 0.9, 0.76],
    )
