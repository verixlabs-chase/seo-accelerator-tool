from __future__ import annotations

from app.intelligence.digital_twin.models.model_registry import get_model_parameters


class ConfidenceEstimator:
    def __init__(self, parameters: dict[str, float] | None = None) -> None:
        if parameters is not None:
            self.parameters = dict(parameters)
            return
        registry_parameters = get_model_parameters().get('confidence_parameters', {})
        self.parameters = dict(registry_parameters)

    def compute_confidence(
        self,
        *,
        pattern_support_count: int,
        historical_outcome_variance: float,
        cohort_confidence: float,
        sample_size: int,
    ) -> float:
        base = self._param('base', 0.45)
        pattern_weight = self._param('pattern_weight', 0.25)
        sample_weight = self._param('sample_weight', 0.30)
        cohort_weight = self._param('cohort_weight', 0.10)
        variance_weight = self._param('variance_weight', 0.10)
        sample_size_norm = max(1.0, self._param('sample_size_norm', 20.0))

        pattern_confidence = min(1.0, max(0.0, float(cohort_confidence)))
        sample_size_factor = min(1.0, max(0.0, float(sample_size) / sample_size_norm))
        support_factor = min(1.0, max(0.0, float(pattern_support_count) / sample_size_norm))
        variance = max(0.0, float(historical_outcome_variance))
        stability_factor = min(1.0, 1.0 / (1.0 + variance))

        confidence = (
            base
            + pattern_confidence * pattern_weight
            + max(sample_size_factor, support_factor) * sample_weight
            + pattern_confidence * cohort_weight
            + stability_factor * variance_weight
        )
        return round(min(0.95, max(0.05, confidence)), 6)

    def _param(self, name: str, fallback: float) -> float:
        return float(self.parameters.get(name, fallback))
