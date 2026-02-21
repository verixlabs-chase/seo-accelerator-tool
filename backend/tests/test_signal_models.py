from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.services.strategy_engine.signal_models import build_signal_model


def test_build_signal_model_normalizes_aliases() -> None:
    model = build_signal_model(
        {
            "gbp_total_views": 1500,
            "gbp_calls": 14,
            "LCP": 2.3,
            "ctr": 0.12,
        }
    )
    assert model.profile_views == 1500
    assert model.phone_calls == 14
    assert model.lcp == 2.3
    assert model.ctr == 0.12


def test_build_signal_model_rejects_unknown_fields() -> None:
    with pytest.raises(ValueError, match="Unknown signal fields"):
        build_signal_model({"unknown_metric": 1})


def test_build_signal_model_enforces_validation() -> None:
    with pytest.raises(ValidationError):
        build_signal_model({"ctr": 1.2})

