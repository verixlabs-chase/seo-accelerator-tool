from app.services.strategy_engine.profile import resolve_strategy_profile


def test_strategy_profile_hash_is_deterministic() -> None:
    profile_a = resolve_strategy_profile('enterprise')
    profile_b = resolve_strategy_profile('enterprise')
    assert profile_a.version_hash() == profile_b.version_hash()


def test_strategy_profile_has_temporal_weights() -> None:
    profile = resolve_strategy_profile('pro')
    assert profile.momentum_weight > 0
    assert profile.volatility_penalty_weight > 0
    assert profile.trend_window_days >= 7
    assert len(profile.confidence_decay_curve) > 0
