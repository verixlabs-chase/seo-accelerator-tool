from typing import Dict, List

PRECISION = 6


def detect_systemic_drift(campaign_momentum_values: List[float]) -> Dict:
    """
    Detect if multiple campaigns trend negatively simultaneously.
    """

    negatives = [m for m in campaign_momentum_values if m < 0]
    negative_ratio = len(negatives) / len(campaign_momentum_values) \
        if campaign_momentum_values else 0.0

    systemic = negative_ratio >= 0.6

    return {
        "negative_ratio": round(negative_ratio, PRECISION),
        "systemic_drift_detected": systemic,
    }