from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.intelligence.diagnostics import (
    run_competitor_diagnostics,
    run_core_web_vitals_diagnostics,
    run_ctr_diagnostics,
    run_gbp_diagnostics,
    run_ranking_diagnostics,
    run_temporal_diagnostics,
)
from app.services.strategy_engine.schemas import DiagnosticResult, StrategyWindow
from app.services.strategy_engine.signal_models import build_signal_model


def collect_legacy_diagnostics(
    *,
    campaign_id: str,
    raw_signals: dict[str, Any],
    db: Session,
    tier: str,
    window: StrategyWindow | None = None,
) -> list[DiagnosticResult]:
    analysis_window = window or _default_window()
    window_reference = f'{analysis_window.date_from.isoformat()}__{analysis_window.date_to.isoformat()}'
    signals = build_signal_model(raw_signals)

    results: list[DiagnosticResult] = []
    results.extend(run_ctr_diagnostics(signals, window_reference=window_reference, tier=tier))
    results.extend(run_core_web_vitals_diagnostics(signals, window_reference=window_reference))
    results.extend(run_ranking_diagnostics(signals, window_reference=window_reference))
    results.extend(run_gbp_diagnostics(signals, window_reference=window_reference, tier=tier))
    if tier == 'enterprise':
        results.extend(run_competitor_diagnostics(signals, window_reference=window_reference))
    results.extend(
        run_temporal_diagnostics(
            db,
            campaign_id=campaign_id,
            window=analysis_window,
            window_reference=window_reference,
            tier=tier,
        )
    )
    return _dedupe(results)


def _dedupe(results: list[DiagnosticResult]) -> list[DiagnosticResult]:
    seen: dict[str, DiagnosticResult] = {}
    for item in results:
        current = seen.get(item.scenario_id)
        if current is None or item.confidence > current.confidence:
            seen[item.scenario_id] = item
    return [seen[key] for key in sorted(seen)]


def _default_window() -> StrategyWindow:
    now = datetime.now(UTC)
    return StrategyWindow(date_from=now.replace(day=1), date_to=now)
