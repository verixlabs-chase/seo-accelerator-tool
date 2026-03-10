from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.intelligence.telemetry.learning_metrics_scheduler import run_daily_learning_snapshot, run_weekly_learning_snapshot
from app.intelligence.telemetry.learning_reports import generate_learning_report
from app.models.learning_metric_snapshot import LearningMetricSnapshot
from app.models.learning_report import LearningReport


def test_generate_learning_report_returns_window_averages_and_trend(db_session) -> None:
    now = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)
    recent_values = [
        (0.8, 0.7, 0.3, 0.9),
        (0.7, 0.65, 0.25, 0.85),
        (0.75, 0.72, 0.28, 0.88),
    ]
    older_values = [
        (0.4, 0.45, 0.05, 0.5),
        (0.5, 0.48, 0.08, 0.55),
        (0.45, 0.42, 0.02, 0.52),
    ]
    for idx, values in enumerate(recent_values):
        db_session.add(
            LearningMetricSnapshot(
                timestamp=now - timedelta(days=idx),
                mutation_success_rate=values[0],
                experiment_win_rate=values[1],
                policy_improvement_velocity=values[2],
                causal_confidence_mean=values[3],
                mutation_count=2,
                experiment_count=2,
            )
        )
    for idx, values in enumerate(older_values, start=10):
        db_session.add(
            LearningMetricSnapshot(
                timestamp=now - timedelta(days=idx),
                mutation_success_rate=values[0],
                experiment_win_rate=values[1],
                policy_improvement_velocity=values[2],
                causal_confidence_mean=values[3],
                mutation_count=2,
                experiment_count=2,
            )
        )
    db_session.commit()

    report = generate_learning_report(db_session, now=now)

    assert report['seven_day_averages']['mutation_success_rate'] == 0.75
    assert report['seven_day_averages']['experiment_win_rate'] == 0.69
    assert report['seven_day_averages']['policy_improvement_velocity'] == 0.276667
    assert report['seven_day_averages']['causal_confidence_mean'] == 0.876667
    assert report['trend_direction'] == 'up'


def test_learning_metrics_scheduler_persists_daily_and_weekly_reports(db_session) -> None:
    now = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)
    db_session.add(
        LearningMetricSnapshot(
            timestamp=now,
            mutation_success_rate=0.5,
            experiment_win_rate=0.6,
            policy_improvement_velocity=0.1,
            causal_confidence_mean=0.7,
            mutation_count=1,
            experiment_count=1,
        )
    )
    db_session.commit()

    daily = run_daily_learning_snapshot(db_session, now=now)
    weekly = run_weekly_learning_snapshot(db_session, now=now)
    db_session.commit()

    assert daily['schedule'] == 'daily'
    assert weekly['schedule'] == 'weekly'
    assert db_session.query(LearningReport).count() == 1
    expected = generate_learning_report(db_session, now=now)['seven_day_averages']
    row = db_session.query(LearningReport).one()
    assert row.report_date.isoformat() == '2026-03-10'
    assert float(row.mutation_success_rate) == float(expected['mutation_success_rate'])
    assert float(row.experiment_win_rate) == float(expected['experiment_win_rate'])
    assert float(row.policy_improvement_velocity) == float(expected['policy_improvement_velocity'])
    assert float(row.causal_confidence_mean) == float(expected['causal_confidence_mean'])
