from app.services.portfolio.allocator import allocate_portfolio_capital


def test_allocator_deterministic_order_and_hash():
    inputs = [
        {"campaign_id": 2, "current_allocation": 0.5, "opportunity_score": 0.2},
        {"campaign_id": 1, "current_allocation": 0.5, "opportunity_score": 0.8},
    ]

    result_a = allocate_portfolio_capital(inputs, max_shift=0.2)
    result_b = allocate_portfolio_capital(list(reversed(inputs)), max_shift=0.2)

    assert result_a["allocations"] == result_b["allocations"]
    assert result_a["hash"] == result_b["hash"]


def test_allocator_enforces_max_shift_bound():
    inputs = [
        {"campaign_id": "a", "current_allocation": 0.9, "opportunity_score": 0.0},
        {"campaign_id": "b", "current_allocation": 0.1, "opportunity_score": 1.0},
    ]

    result = allocate_portfolio_capital(inputs, max_shift=0.2)
    by_id = {row["campaign_id"]: row for row in result["allocations"]}

    assert by_id["a"]["allocation"] == 0.7
    assert by_id["b"]["allocation"] == 0.3
    assert abs(by_id["a"]["delta"]) <= 0.2
    assert abs(by_id["b"]["delta"]) <= 0.2


def test_allocator_normalizes_to_one_with_fixed_precision():
    inputs = [
        {"campaign_id": 10, "current_allocation": 0.0, "opportunity_score": 3.0},
        {"campaign_id": 20, "current_allocation": 0.0, "opportunity_score": 1.0},
        {"campaign_id": 30, "current_allocation": 0.0, "opportunity_score": 2.0},
    ]

    result = allocate_portfolio_capital(inputs, max_shift=1.0)

    assert result["allocation_sum"] == 1.0
    assert sum(item["allocation"] for item in result["allocations"]) == 1.0