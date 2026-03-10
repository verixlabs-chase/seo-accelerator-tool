from app.intelligence.digital_twin.models.confidence_estimator import ConfidenceEstimator
from app.intelligence.digital_twin.models.model_registry import reset_model_registry


def test_confidence_estimator_is_deterministic_and_bounded(db_session) -> None:
    reset_model_registry()
    estimator = ConfidenceEstimator()

    first = estimator.compute_confidence(
        pattern_support_count=12,
        historical_outcome_variance=0.2,
        cohort_confidence=0.8,
        sample_size=18,
    )
    second = estimator.compute_confidence(
        pattern_support_count=12,
        historical_outcome_variance=0.2,
        cohort_confidence=0.8,
        sample_size=18,
    )

    assert first == second
    assert 0.05 <= first <= 0.95
    assert first == 0.95
