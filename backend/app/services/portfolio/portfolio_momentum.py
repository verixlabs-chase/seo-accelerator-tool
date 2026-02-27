from hashlib import sha256
import json
from typing import Dict, List

PRECISION = 6
PORTFOLIO_MOMENTUM_VERSION = "v1"


def compute_campaign_weighted_momentum(campaign_metrics: List[Dict]) -> Dict:
    """
    campaign_metrics: [
        {
            "campaign_id": int,
            "momentum_score": float,
            "opportunity_score": float,
            "traffic_weight": float
        }
    ]
    """

    weighted_sum = 0.0
    total_weight = 0.0

    for c in sorted(campaign_metrics, key=lambda x: x["campaign_id"]):
        weight = max(c["traffic_weight"], 0.0)
        weighted_sum += round(c["momentum_score"], PRECISION) * weight
        total_weight += weight

    portfolio_momentum = round(
        weighted_sum / total_weight, PRECISION
    ) if total_weight > 0 else 0.0

    payload = {
        "version": PORTFOLIO_MOMENTUM_VERSION,
        "portfolio_momentum": portfolio_momentum,
        "campaign_count": len(campaign_metrics),
    }

    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    payload["hash"] = sha256(serialized.encode()).hexdigest()

    return payload