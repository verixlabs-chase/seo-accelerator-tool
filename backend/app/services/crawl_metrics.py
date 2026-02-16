from __future__ import annotations

from dataclasses import dataclass, asdict
from threading import Lock
from time import perf_counter


@dataclass
class StageMetric:
    calls: int = 0
    failures: int = 0
    total_ms: float = 0.0
    p95_ms: float = 0.0


_lock = Lock()
_stage_metrics: dict[str, StageMetric] = {}
_durations: dict[str, list[float]] = {}

_SLOS_MS = {
    "crawl.schedule_campaign": 200.0,
    "crawl.fetch_batch": 30000.0,
    "crawl.parse_page": 2000.0,
    "crawl.extract_issues": 1000.0,
    "crawl.finalize_run": 500.0,
}


def stage_timer(stage: str):
    start = perf_counter()

    class _Timer:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, _exc, _tb):
            duration_ms = (perf_counter() - start) * 1000.0
            observe(stage, duration_ms, success=exc_type is None)
            return False

    return _Timer()


def observe(stage: str, duration_ms: float, success: bool) -> None:
    with _lock:
        metric = _stage_metrics.get(stage)
        if metric is None:
            metric = StageMetric()
            _stage_metrics[stage] = metric
            _durations[stage] = []
        metric.calls += 1
        if not success:
            metric.failures += 1
        metric.total_ms += duration_ms
        durs = _durations[stage]
        durs.append(duration_ms)
        if len(durs) > 1000:
            del durs[:200]
        sorted_durs = sorted(durs)
        idx = int(max(0, min(len(sorted_durs) - 1, round(0.95 * (len(sorted_durs) - 1)))))
        metric.p95_ms = sorted_durs[idx]


def snapshot() -> dict:
    with _lock:
        stages = {}
        for name, metric in _stage_metrics.items():
            avg_ms = metric.total_ms / metric.calls if metric.calls else 0.0
            slo_ms = _SLOS_MS.get(name)
            stages[name] = {
                **asdict(metric),
                "avg_ms": round(avg_ms, 2),
                "slo_ms": slo_ms,
                "slo_ok": True if slo_ms is None else metric.p95_ms <= slo_ms,
            }
        return {"stages": stages}

