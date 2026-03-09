from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

PSEUDOCODE = """
1. Accept high-confidence patterns from strategy_pattern_discovery.
2. Convert each pattern into a stable strategy_id and structured mutation template.
3. Emit hypotheses only when support and confidence exceed minimum thresholds.
4. Hand accepted hypotheses to strategy evolution and digital twin validation.
"""


@dataclass(slots=True)
class StrategyHypothesis:
    strategy_id: str
    description: str
    mutation_pattern: dict[str, object]
    source_pattern_id: str
    confidence_score: float
    support_count: int


def generate_strategy_hypotheses(
    patterns: list[dict[str, Any]],
    *,
    minimum_confidence: float = 0.6,
    minimum_support: int = 3,
) -> list[dict[str, Any]]:
    hypotheses: list[StrategyHypothesis] = []
    for pattern in patterns:
        confidence = float(pattern.get('confidence_score', 0.0) or 0.0)
        support_count = int(pattern.get('support_count', 0) or 0)
        if confidence < minimum_confidence or support_count < minimum_support:
            continue
        pattern_id = str(pattern.get('pattern_id') or 'derived_pattern').strip().lower()
        hypotheses.append(
            StrategyHypothesis(
                strategy_id=pattern_id,
                description=str(pattern.get('description') or pattern_id.replace('_', ' ')),
                mutation_pattern=dict(pattern.get('mutation_pattern') or {}),
                source_pattern_id=pattern_id,
                confidence_score=round(confidence, 6),
                support_count=support_count,
            )
        )
    return [asdict(item) for item in hypotheses]
