from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.intelligence.digital_twin.strategy_simulation_engine import simulate_strategy
from app.intelligence.digital_twin.twin_state_model import DigitalTwinState
from app.intelligence.global_graph.graph_service import get_graph_query_engine


class StrategyQueryEngine(Protocol):
    def get_relevant_strategies(
        self,
        campaign_id: str,
        industry: str | None = None,
        top_k: int = 10,
        min_confidence: float = 0.0,
    ) -> list[dict[str, Any]]:
        ...



@dataclass(frozen=True)
class TransferCandidate:
    strategy_id: str
    strategy_actions: list[dict[str, object]]
    evidence: list[dict[str, Any]]
    graph_score: float


def transfer_strategies(
    campaign_id: str,
    *,
    db: Session | None = None,
    industry: str | None = None,
    top_k: int = 10,
    min_confidence: float = 0.0,
    query_engine: StrategyQueryEngine | None = None,
    simulate_fn: Callable[..., dict[str, Any]] | None = None,
    twin_state_builder: Callable[[Session, str], Any] | None = None,
    persist_simulations: bool = False,
) -> dict[str, list[Any]]:
    owns_session = db is None
    session = db or SessionLocal()
    try:
        graph = query_engine or get_graph_query_engine()
        raw_strategies = graph.get_relevant_strategies(
            campaign_id=campaign_id,
            industry=industry,
            top_k=top_k,
            min_confidence=min_confidence,
        )
        if not raw_strategies:
            return {'strategies': [], 'evidence': [], 'confidence_scores': []}

        builder = twin_state_builder or DigitalTwinState.from_campaign_data
        twin_state = builder(session, campaign_id)

        simulator = simulate_fn or simulate_strategy
        candidates = [_to_candidate(item) for item in raw_strategies]
        results: list[dict[str, Any]] = []

        for candidate in candidates:
            simulation = simulator(
                twin_state,
                candidate.strategy_actions,
                db=session if persist_simulations else None,
                strategy_id=candidate.strategy_id,
            )
            results.append(
                {
                    'strategy_id': candidate.strategy_id,
                    'strategy_actions': candidate.strategy_actions,
                    'graph_score': round(float(candidate.graph_score), 6),
                    'simulation': simulation,
                    'confidence': round(float(simulation.get('confidence', 0.0)), 6),
                    'expected_value': round(float(simulation.get('expected_value', 0.0)), 6),
                    'evidence': candidate.evidence,
                }
            )

        ranked = sorted(
            results,
            key=lambda item: (
                float(item.get('confidence', 0.0)),
                float(item.get('expected_value', 0.0)),
                float(item.get('graph_score', 0.0)),
                str(item.get('strategy_id', '')),
            ),
            reverse=True,
        )

        if owns_session and persist_simulations:
            session.commit()

        return {
            'strategies': ranked,
            'evidence': [item.get('evidence', []) for item in ranked],
            'confidence_scores': [float(item.get('confidence', 0.0)) for item in ranked],
        }
    finally:
        if owns_session:
            session.close()



def _to_candidate(payload: dict[str, Any]) -> TransferCandidate:
    strategy_id = str(payload.get('strategy_id', '') or '')
    if not strategy_id:
        raise ValueError('strategy_id is required for transfer candidate')

    evidence = payload.get('evidence') if isinstance(payload.get('evidence'), list) else []
    graph_score = float(payload.get('score', 0.0) or 0.0)
    actions = _build_strategy_actions(strategy_id, evidence, graph_score)
    return TransferCandidate(
        strategy_id=strategy_id,
        strategy_actions=actions,
        evidence=evidence,
        graph_score=graph_score,
    )


def _build_strategy_actions(
    strategy_id: str,
    evidence: list[dict[str, Any]],
    graph_score: float,
) -> list[dict[str, object]]:
    support_count = _sum_support_count(evidence)
    cohort_confidence = _average_confidence(evidence)
    normalized = strategy_id.lower()

    if 'internal' in normalized:
        count = max(3, min(50, support_count * 2))
        return [
            {
                'type': 'internal_link',
                'count': count,
                'pattern_support_count': support_count,
                'cohort_confidence': cohort_confidence,
            }
        ]

    if 'content' in normalized or 'publish' in normalized:
        pages = max(1, min(20, int(round(max(1.0, graph_score)))))
        return [
            {
                'type': 'publish_content',
                'pages': pages,
                'pattern_support_count': support_count,
                'cohort_confidence': cohort_confidence,
            }
        ]

    if 'schema' in normalized or 'technical' in normalized:
        count = max(1, min(10, support_count))
        return [
            {
                'type': 'fix_technical_issues',
                'count': count,
                'pattern_support_count': support_count,
                'cohort_confidence': cohort_confidence,
            }
        ]

    return [
        {
            'type': 'publish_content',
            'pages': 1,
            'pattern_support_count': support_count,
            'cohort_confidence': cohort_confidence,
        }
    ]


def _sum_support_count(evidence: list[dict[str, Any]]) -> int:
    total = 0
    for item in evidence:
        try:
            total += max(0, int(item.get('support_count', 1)))
        except (TypeError, ValueError, AttributeError):
            total += 1
    return max(total, 1)


def _average_confidence(evidence: list[dict[str, Any]]) -> float:
    if not evidence:
        return 0.5

    values: list[float] = []
    for item in evidence:
        try:
            values.append(float(item.get('confidence', 0.5)))
        except (TypeError, ValueError, AttributeError):
            continue

    if not values:
        return 0.5
    return max(0.0, min(1.0, sum(values) / len(values)))
