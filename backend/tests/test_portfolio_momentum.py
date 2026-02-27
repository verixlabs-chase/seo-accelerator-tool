from app.services.portfolio.portfolio_momentum import compute_campaign_weighted_momentum


def test_portfolio_momentum_deterministic():
    input_a = [
        {"campaign_id": 2, "momentum_score": 0.5, "opportunity_score": 1, "traffic_weight": 10},
        {"campaign_id": 1, "momentum_score": 1.0, "opportunity_score": 1, "traffic_weight": 5},
    ]

    result_a = compute_campaign_weighted_momentum(input_a)
    result_b = compute_campaign_weighted_momentum(list(reversed(input_a)))

    assert result_a["portfolio_momentum"] == result_b["portfolio_momentum"]
    assert result_a["hash"] == result_b["hash"]