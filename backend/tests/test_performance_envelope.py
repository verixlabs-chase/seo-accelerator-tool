from scripts.load_profile import run_load_profile


def test_lightweight_performance_envelope() -> None:
    summary = run_load_profile(
        location_create_concurrency=8,
        mixed_iterations=8,
        provider_iterations=4,
    )

    assert summary["p95"] < 250.0
    assert summary["error_rate"] < 0.01
    assert summary["throughput_rps"] > 0
