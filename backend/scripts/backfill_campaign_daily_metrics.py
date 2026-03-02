from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402
from app.services import analytics_service  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Deterministically backfill campaign_daily_metrics for a date range.')
    parser.add_argument('--start', required=True, dest='date_from', help='Inclusive start date in YYYY-MM-DD format')
    parser.add_argument('--end', required=True, dest='date_to', help='Inclusive end date in YYYY-MM-DD format')
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    db = SessionLocal()
    try:
        result = analytics_service.rollup_campaign_daily_metrics_for_range(
            db=db,
            date_from=args.date_from,
            date_to=args.date_to,
        )
        print(
            json.dumps(
                {
                    'date_from': result.date_from.isoformat(),
                    'date_to': result.date_to.isoformat(),
                    'days_processed': result.days_processed,
                    'processed_campaigns': result.processed_campaigns,
                    'inserted_rows': result.inserted_rows,
                    'updated_rows': result.updated_rows,
                    'skipped_rows': result.skipped_rows,
                },
                sort_keys=True,
            )
        )
        return 0
    finally:
        db.close()


if __name__ == '__main__':
    raise SystemExit(main())
