from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session


pytestmark = pytest.mark.postgres_required


def _run_alembic(backend_dir: Path, database_url: str, *args: str) -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    env["POSTGRES_DSN"] = database_url
    subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=str(backend_dir),
        env=env,
        check=True,
    )


def test_existing_append_only_ledger_rows_receive_usage_credits(
    apply_migrations: dict[str, object],
    db_session: Session,
) -> None:
    database_url = str(apply_migrations["database_url"])
    backend_dir = Path(__file__).resolve().parents[2]
    engine = create_engine(database_url)
    ledger_id = str(uuid.uuid4())

    organization_id = db_session.execute(
        text("SELECT id FROM organizations ORDER BY id LIMIT 1")
    ).scalar_one()
    db_session.commit()
    db_session.close()

    _run_alembic(backend_dir, database_url, "downgrade", "20260804_0089")

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO cost_ledger_entries (
                    id,
                    organization_id,
                    provider_name,
                    capability,
                    operation,
                    credential_owner,
                    quantity,
                    unit,
                    estimated_cost,
                    budget_impact_cost,
                    status,
                    event_type,
                    idempotency_key,
                    price_card_version,
                    plan_code,
                    plan_revenue_snapshot
                ) VALUES (
                    :id,
                    :organization_id,
                    'migration-test',
                    'keyword-research',
                    'backfill',
                    'platform',
                    1,
                    'request',
                    0.025,
                    0.025,
                    'reserved',
                    'reservation',
                    :idempotency_key,
                    'migration-test-v1',
                    'solo',
                    299.00
                )
                """
            ),
            {
                "id": ledger_id,
                "organization_id": organization_id,
                "idempotency_key": f"migration-test-{ledger_id}",
            },
        )

    _run_alembic(backend_dir, database_url, "upgrade", "head")

    with engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT customer_credit_units, credit_policy_version
                FROM cost_ledger_entries
                WHERE id = :id
                """
            ),
            {"id": ledger_id},
        ).one()
    assert row.customer_credit_units == 3
    assert row.credit_policy_version == "insight-credits-2026-08-v1"

    with pytest.raises(DBAPIError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    UPDATE cost_ledger_entries
                    SET customer_credit_units = 99
                    WHERE id = :id
                    """
                ),
                {"id": ledger_id},
            )

    engine.dispose()
