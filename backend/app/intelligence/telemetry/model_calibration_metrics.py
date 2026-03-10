from __future__ import annotations

from statistics import mean
from typing import Any

from sqlalchemy.orm import Session

from app.models.digital_twin_simulation import DigitalTwinSimulation
from app.models.recommendation_outcome import RecommendationOutcome


def snapshot_model_calibration_metrics(db: Session) -> dict[str, Any]:
    simulations = db.query(DigitalTwinSimulation).all()
    outcomes = db.query(RecommendationOutcome).all()
    expected = [float(row.expected_impact or 0.0) for row in simulations]
    actual = [float(row.delta or 0.0) for row in outcomes]
    expected_mean = mean(expected) if expected else 0.0
    actual_mean = mean(actual) if actual else 0.0
    return {
        'simulation_accuracy': round(actual_mean - expected_mean, 6),
        'model_calibration_drift': round(abs(actual_mean - expected_mean), 6),
        'simulation_count': len(simulations),
        'outcome_count': len(outcomes),
    }
