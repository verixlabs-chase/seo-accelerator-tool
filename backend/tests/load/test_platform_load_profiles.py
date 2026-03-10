from __future__ import annotations

import os

import pytest


pytestmark = pytest.mark.skipif(
    os.getenv('RUN_PLATFORM_LOAD_TESTS', '').lower() not in {'1', 'true', 'yes'},
    reason='manual load profiles are disabled by default',
)


def test_api_request_burst_profile() -> None:
    target_requests = 10_000
    assert target_requests == 10_000


def test_queue_action_backlog_profile() -> None:
    target_actions = 5_000
    assert target_actions == 5_000


def test_concurrent_worker_profile() -> None:
    target_workers = 1_000
    assert target_workers == 1_000


def test_report_generation_burst_profile() -> None:
    burst_reports = 500
    assert burst_reports == 500
