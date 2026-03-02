from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from time import monotonic, sleep
from typing import Callable

Operation = Callable[[], None]


def _default_location_create() -> None:
    sleep(0.003)


def _default_read() -> None:
    sleep(0.001)


def _default_provider_call() -> None:
    sleep(0.006)


def run_load_profile(
    *,
    location_create_concurrency: int = 100,
    mixed_iterations: int = 40,
    provider_iterations: int = 20,
    location_create_operation: Operation | None = None,
    read_operation: Operation | None = None,
    provider_operation: Operation | None = None,
) -> dict[str, float]:
    location_create_operation = location_create_operation or _default_location_create
    read_operation = read_operation or _default_read
    provider_operation = provider_operation or _default_provider_call

    samples: list[float] = []
    failures = 0
    synthetic_queue_backlog = 0
    started_at = monotonic()

    def _timed(op: Operation) -> float:
        op_started_at = monotonic()
        op()
        return (monotonic() - op_started_at) * 1000.0

    with ThreadPoolExecutor(max_workers=max(1, location_create_concurrency)) as executor:
        futures = [executor.submit(_timed, location_create_operation) for _ in range(location_create_concurrency)]
        for future in as_completed(futures):
            try:
                samples.append(future.result())
            except Exception:
                failures += 1
                synthetic_queue_backlog += 1

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = []
        for index in range(max(1, mixed_iterations)):
            op = read_operation if index % 2 == 0 else location_create_operation
            futures.append(executor.submit(_timed, op))
        for future in as_completed(futures):
            try:
                samples.append(future.result())
            except Exception:
                failures += 1
                synthetic_queue_backlog += 1

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(_timed, provider_operation) for _ in range(max(1, provider_iterations))]
        for future in as_completed(futures):
            try:
                samples.append(future.result())
            except Exception:
                failures += 1
                synthetic_queue_backlog += 1

    total_operations = len(samples) + failures
    elapsed_seconds = max(0.001, monotonic() - started_at)
    throughput_rps = total_operations / elapsed_seconds

    return {
        "p50": round(_percentile(samples, 50), 2),
        "p95": round(_percentile(samples, 95), 2),
        "p99": round(_percentile(samples, 99), 2),
        "error_rate": round((failures / total_operations) if total_operations else 0.0, 4),
        "throughput_rps": round(throughput_rps, 2),
        "queue_backlog_growth": float(synthetic_queue_backlog),
    }


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = ((percentile / 100.0) * (len(ordered) - 1))
    lower = int(rank)
    upper = min(len(ordered) - 1, lower + 1)
    weight = rank - lower
    return ordered[lower] + ((ordered[upper] - ordered[lower]) * weight)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a lightweight load profile harness.")
    parser.add_argument("--location-create-concurrency", type=int, default=100)
    parser.add_argument("--mixed-iterations", type=int, default=40)
    parser.add_argument("--provider-iterations", type=int, default=20)
    args = parser.parse_args()

    summary = run_load_profile(
        location_create_concurrency=max(1, args.location_create_concurrency),
        mixed_iterations=max(1, args.mixed_iterations),
        provider_iterations=max(1, args.provider_iterations),
    )
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
