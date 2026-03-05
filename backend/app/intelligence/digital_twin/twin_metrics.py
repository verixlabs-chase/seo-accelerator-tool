from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.intelligence.intelligence_metrics_aggregator import compute_campaign_metrics


@dataclass
class TwinMetricsTracker:
    simulations_run: int = 0
    optimizer_decisions: int = 0
    total_predicted_rank_delta: float = 0.0
    total_confidence: float = 0.0

    def record_simulation(self, *, predicted_rank_delta: float, confidence: float) -> None:
        self.simulations_run += 1
        self.total_predicted_rank_delta += float(predicted_rank_delta)
        self.total_confidence += float(confidence)

    def record_optimizer_decision(self) -> None:
        self.optimizer_decisions += 1

    @property
    def avg_predicted_rank_delta(self) -> float:
        if self.simulations_run == 0:
            return 0.0
        return round(self.total_predicted_rank_delta / self.simulations_run, 6)

    @property
    def avg_confidence(self) -> float:
        if self.simulations_run == 0:
            return 0.0
        return round(self.total_confidence / self.simulations_run, 6)

    def snapshot(self) -> dict[str, float | int]:
        return {
            'simulations_run': self.simulations_run,
            'optimizer_decisions': self.optimizer_decisions,
            'avg_predicted_rank_delta': self.avg_predicted_rank_delta,
            'avg_confidence': self.avg_confidence,
        }


def sync_with_intelligence_metrics_snapshot(
    db: Session,
    *,
    campaign_id: str,
    tracker: TwinMetricsTracker,
) -> dict[str, float | int]:
    snapshot_date = datetime.now(UTC).date()
    row = compute_campaign_metrics(campaign_id, db=db, metric_date=snapshot_date)

    payload = tracker.snapshot()
    payload['metrics_snapshot_id'] = row.id
    payload['metrics_snapshot_date'] = row.metric_date.isoformat()
    return payload
