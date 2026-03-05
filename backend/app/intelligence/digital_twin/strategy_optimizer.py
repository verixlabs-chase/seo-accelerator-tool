from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy.orm import Session

from app.intelligence.digital_twin.strategy_simulation_engine import simulate_strategy
from app.intelligence.digital_twin.twin_state_model import DigitalTwinState
from app.models.digital_twin_simulation import DigitalTwinSimulation


def optimize_strategy(
    twin_state: DigitalTwinState,
    candidate_strategies: Iterable[dict[str, Any]],
    *,
    db: Session | None = None,
) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None

    for index, strategy in enumerate(candidate_strategies):
        strategy_id = str(strategy.get('strategy_id', strategy.get('scenario_id', f'strategy_{index}')))
        strategy_actions = strategy.get('strategy_actions') or []
        simulation = simulate_strategy(
            twin_state,
            strategy_actions,
            db=db,
            strategy_id=strategy_id,
        )
        expected_value = float(simulation.get('expected_value', 0.0))

        result = {
            'strategy_id': strategy_id,
            'strategy': strategy,
            'simulation': simulation,
            'expected_value': round(expected_value, 6),
            'strategy_index': index,
        }

        if best is None:
            best = result
            continue

        is_better = result['expected_value'] > best['expected_value']
        tie_break = result['expected_value'] == best['expected_value'] and strategy_id < str(best['strategy_id'])
        if is_better or tie_break:
            best = result

    if best is not None and db is not None:
        simulation_id = best['simulation'].get('simulation_id')
        if simulation_id:
            row = db.get(DigitalTwinSimulation, str(simulation_id))
            if row is not None:
                row.selected_strategy = True
                db.flush()

    return best
