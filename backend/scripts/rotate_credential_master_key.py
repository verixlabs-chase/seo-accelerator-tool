from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.crypto import decrypt_payload, encrypt_payload, get_master_keys
from app.db.session import _normalize_postgres_dsn
from app.models.organization_oauth_client import OrganizationOAuthClient
from app.models.organization_provider_credential import OrganizationProviderCredential
from app.models.platform_provider_credential import PlatformProviderCredential


_CREDENTIAL_MODELS = (
    OrganizationOAuthClient,
    OrganizationProviderCredential,
    PlatformProviderCredential,
)


def rewrap_credentials(
    db: Session,
    *,
    apply_changes: bool,
) -> dict[str, Any]:
    get_master_keys()
    counts: dict[str, int] = {}
    failures: list[dict[str, str]] = []
    updated_at = datetime.now(UTC)
    for model in _CREDENTIAL_MODELS:
        table_name = str(model.__tablename__)
        rows = db.query(model).order_by(model.id.asc()).all()
        counts[table_name] = len(rows)
        for row in rows:
            try:
                plaintext = decrypt_payload(row.encrypted_secret_blob)
                if apply_changes:
                    encrypted_blob, key_reference, key_version = encrypt_payload(plaintext)
                    if decrypt_payload(encrypted_blob) != plaintext:
                        raise RuntimeError("Rewrapped credential failed verification.")
                    row.encrypted_secret_blob = encrypted_blob
                    row.key_reference = key_reference
                    row.key_version = key_version
                    row.updated_at = updated_at
            except Exception as exc:  # noqa: BLE001
                failures.append(
                    {
                        "table": table_name,
                        "reason": type(exc).__name__,
                    }
                )
    if failures:
        db.rollback()
    elif apply_changes:
        db.commit()
    else:
        db.rollback()
    return {
        "passed": not failures,
        "mode": "apply" if apply_changes else "dry_run",
        "key_version": os.getenv("CREDENTIAL_MASTER_KEY_VERSION", "v1"),
        "credential_counts": counts,
        "total_credentials": sum(counts.values()),
        "failures": failures,
        "plaintext_logged": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify or rewrap stored provider credentials during a PLATFORM_MASTER_KEY "
            "rotation. Plaintext credentials are never printed."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist rewrapped credential blobs. The default is a rollback-only dry run.",
    )
    parser.add_argument(
        "--confirm-version",
        default="",
        help="Required with --apply and must equal CREDENTIAL_MASTER_KEY_VERSION.",
    )
    parser.add_argument(
        "--output",
        help="Optional path for the JSON evidence. Parent directories are created.",
    )
    args = parser.parse_args()

    database_url = os.getenv("CREDENTIAL_ROTATION_DATABASE_URL", "").strip()
    if not database_url:
        raise SystemExit(
            "CREDENTIAL_ROTATION_DATABASE_URL is required; keep database credentials "
            "out of command history."
        )
    expected_version = os.getenv("CREDENTIAL_MASTER_KEY_VERSION", "v1").strip()
    if args.apply and args.confirm_version != expected_version:
        raise SystemExit(
            "--confirm-version must match CREDENTIAL_MASTER_KEY_VERSION before writes are allowed."
        )

    engine = create_engine(
        _normalize_postgres_dsn(database_url),
        pool_pre_ping=True,
        connect_args={"prepare_threshold": None},
    )
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = session_local()
    try:
        result = rewrap_credentials(db, apply_changes=args.apply)
    finally:
        db.close()
        engine.dispose()
    rendered = json.dumps(result, indent=2, sort_keys=True, default=str)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
