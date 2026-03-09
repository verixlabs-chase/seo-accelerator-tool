from __future__ import annotations

from dataclasses import asdict, dataclass
import statistics
from typing import Any

from sqlalchemy.orm import Session

from app.intelligence.network_learning.industry_similarity_engine import similarity_allows_transfer
from app.models.seo_mutation_outcome import SEOMutationOutcome

PSEUDOCODE = """
1. Load mutation outcomes grouped by mutation_type and industry.
2. Exclude source industries that fail the similarity gate for the target industry.
3. Compute support_count, average_rank_delta, average_traffic_delta, variance, and outlier rate.
4. Convert those signals into a confidence_score.
5. Mark negative strategies when mean rank delta degrades rankings consistently.
6. Emit summaries to the hypothesis and graph integration layers.
"""


@dataclass(slots=True)
class MutationCausalSummary:
    mutation_type: str
    industry_id: str
    support_count: int
    average_rank_delta: float
    average_traffic_delta: float
    variance: float
    confidence_score: float
    positive_consistency: float
    outlier_rate: float
    negative_strategy: bool


def summarize_mutation_causality(
    db: Session,
    *,
    target_industry_id: str | None = None,
    minimum_support: int = 3,
) -> list[dict[str, Any]]:
    rows = db.query(SEOMutationOutcome).order_by(SEOMutationOutcome.recorded_at.desc()).all()
    grouped: dict[tuple[str, str], list[SEOMutationOutcome]] = {}
    for row in rows:
        source_industry = str(row.industry_id or 'unknown')
        if target_industry_id and not similarity_allows_transfer(db, source_industry, target_industry_id):
            continue
        key = (str(row.mutation_type), source_industry)
        grouped.setdefault(key, []).append(row)

    summaries: list[MutationCausalSummary] = []
    for (mutation_type, industry_id), items in grouped.items():
        if len(items) < minimum_support:
            continue
        rank_deltas = [float(item.rank_after) - float(item.rank_before) for item in items]
        traffic_deltas = [float(item.traffic_after) - float(item.traffic_before) for item in items]
        positive_consistency = sum(1 for item in rank_deltas if item < 0.0) / len(rank_deltas)
        outlier_rate = _outlier_rate(rank_deltas)
        variance = statistics.pvariance(rank_deltas) if len(rank_deltas) > 1 else 0.0
        average_rank_delta = sum(rank_deltas) / len(rank_deltas)
        average_traffic_delta = sum(traffic_deltas) / len(traffic_deltas)
        confidence_score = _confidence_score(len(items), variance, positive_consistency, outlier_rate)
        summaries.append(
            MutationCausalSummary(
                mutation_type=mutation_type,
                industry_id=industry_id,
                support_count=len(items),
                average_rank_delta=round(average_rank_delta, 6),
                average_traffic_delta=round(average_traffic_delta, 6),
                variance=round(variance, 6),
                confidence_score=round(confidence_score, 6),
                positive_consistency=round(positive_consistency, 6),
                outlier_rate=round(outlier_rate, 6),
                negative_strategy=average_rank_delta > 0.0 and positive_consistency < 0.35,
            )
        )
    return [asdict(item) for item in sorted(summaries, key=lambda item: (item.confidence_score, item.support_count), reverse=True)]


def _confidence_score(support_count: int, variance: float, positive_consistency: float, outlier_rate: float) -> float:
    support_factor = min(1.0, float(support_count) / 25.0)
    variance_penalty = min(0.5, max(0.0, variance) / 20.0)
    outlier_penalty = min(0.3, max(0.0, outlier_rate) * 0.5)
    score = 0.35 + support_factor * 0.35 + positive_consistency * 0.35 - variance_penalty - outlier_penalty
    return max(0.0, min(0.99, score))


def _outlier_rate(values: list[float]) -> float:
    if len(values) < 4:
        return 0.0
    mean = sum(values) / len(values)
    variance = statistics.pvariance(values)
    if variance <= 0.0:
        return 0.0
    stdev = variance ** 0.5
    threshold = 2.0 * stdev
    outliers = sum(1 for value in values if abs(value - mean) > threshold)
    return outliers / len(values)
