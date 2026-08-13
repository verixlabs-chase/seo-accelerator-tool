from __future__ import annotations

import hashlib
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.core.crypto import decrypt_payload, encrypt_payload
from app.models.campaign import Campaign
from app.models.wordpress_site_connection import WordPressSiteConnection


PAIRING_LIFETIME_MINUTES = 10


class WordPressConnectionError(RuntimeError):
    def __init__(self, message: str, *, reason_code: str, status_code: int = 409) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.status_code = status_code


def start_pairing(db: Session, *, campaign: Campaign) -> dict[str, Any]:
    if not campaign.organization_id:
        raise WordPressConnectionError(
            "Connect this business to an organization before pairing WordPress.",
            reason_code="wordpress_organization_required",
        )

    raw_code = secrets.token_hex(12).upper()
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=PAIRING_LIFETIME_MINUTES)
    row = get_site_connection(db, campaign_id=campaign.id)
    if row is None:
        row = WordPressSiteConnection(
            id=str(uuid.uuid4()),
            tenant_id=campaign.tenant_id,
            organization_id=campaign.organization_id,
            campaign_id=campaign.id,
            site_url=_canonical_site_url(campaign.domain),
            status="pending",
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    else:
        row.site_url = _canonical_site_url(campaign.domain)
        row.updated_at = now
        if row.status != "connected":
            row.status = "pending"

    row.pairing_code_hash = _pairing_code_hash(raw_code)
    row.pairing_expires_at = expires_at
    # The API adds the audit event in the same transaction.  Flushing here
    # keeps the pairing code and its audit record atomic under PostgreSQL RLS.
    db.flush()
    db.refresh(row)
    return {
        "campaign_id": campaign.id,
        "site_url": row.site_url,
        "pairing_code": _format_pairing_code(raw_code),
        "expires_at": expires_at.isoformat(),
        "replaces_existing_connection": row.encrypted_secret_blob is not None,
    }


def exchange_pairing(
    db: Session,
    *,
    pairing_code: str,
    site_url: str,
    plugin_version: str,
) -> dict[str, Any]:
    normalized_code = _normalize_pairing_code(pairing_code)
    if len(normalized_code) != 24:
        raise WordPressConnectionError(
            "That pairing code is not valid. Create a new code in InsightOS.",
            reason_code="wordpress_pairing_code_invalid",
            status_code=404,
        )
    row = (
        db.query(WordPressSiteConnection)
        .filter(
            WordPressSiteConnection.pairing_code_hash
            == _pairing_code_hash(normalized_code)
        )
        .first()
    )
    if row is None:
        raise WordPressConnectionError(
            "That pairing code is no longer available. Create a new code in InsightOS.",
            reason_code="wordpress_pairing_code_invalid",
            status_code=404,
        )
    now = datetime.now(UTC)
    expires_at = _as_utc(row.pairing_expires_at)
    if expires_at is None or expires_at <= now:
        row.pairing_code_hash = None
        row.pairing_expires_at = None
        row.updated_at = now
        db.commit()
        raise WordPressConnectionError(
            "That pairing code expired. Create a new code in InsightOS.",
            reason_code="wordpress_pairing_code_expired",
            status_code=410,
        )
    if _normalized_host(site_url) != _normalized_host(row.site_url):
        raise WordPressConnectionError(
            "This pairing code was created for a different website.",
            reason_code="wordpress_pairing_site_mismatch",
            status_code=403,
        )

    plugin_token = secrets.token_urlsafe(32)
    shared_secret = secrets.token_urlsafe(48)
    credentials = {
        "base_url": _canonical_site_url(site_url),
        "plugin_token": plugin_token,
        "shared_secret": shared_secret,
        "plugin_version": plugin_version.strip(),
        "timeout_seconds": 15,
    }
    encrypted_secret_blob, key_reference, key_version = encrypt_payload(credentials)
    replacing = row.encrypted_secret_blob is not None
    row.site_url = credentials["base_url"]
    row.status = "connected"
    row.pairing_code_hash = None
    row.pairing_expires_at = None
    row.encrypted_secret_blob = encrypted_secret_blob
    row.key_reference = key_reference
    row.key_version = key_version
    row.plugin_version = plugin_version.strip() or None
    row.paired_at = now
    row.disconnected_at = None
    row.last_rotated_at = now if replacing else None
    row.updated_at = now
    # The public exchange endpoint supplies its narrowly scoped database
    # security context and commits after adding the tenant audit event.
    db.flush()
    return {
        "connected": True,
        "campaign_id": row.campaign_id,
        "site_url": row.site_url,
        "plugin_token": plugin_token,
        "shared_secret": shared_secret,
    }


def get_site_connection(db: Session, *, campaign_id: str) -> WordPressSiteConnection | None:
    return (
        db.query(WordPressSiteConnection)
        .filter(WordPressSiteConnection.campaign_id == campaign_id)
        .first()
    )


def get_site_credentials(db: Session, *, campaign_id: str) -> dict[str, Any]:
    row = get_site_connection(db, campaign_id=campaign_id)
    if row is None or row.status != "connected" or not row.encrypted_secret_blob:
        return {}
    return decrypt_payload(row.encrypted_secret_blob)


def disconnect_site(db: Session, *, campaign_id: str) -> bool:
    row = get_site_connection(db, campaign_id=campaign_id)
    if row is None:
        return False
    now = datetime.now(UTC)
    row.status = "disconnected"
    row.pairing_code_hash = None
    row.pairing_expires_at = None
    row.encrypted_secret_blob = None
    row.key_reference = None
    row.key_version = None
    row.disconnected_at = now
    row.updated_at = now
    # The API commits this state together with its audit event.
    db.flush()
    return True


def pairing_is_active(row: WordPressSiteConnection | None) -> bool:
    if row is None or not row.pairing_code_hash:
        return False
    expires_at = _as_utc(row.pairing_expires_at)
    return bool(expires_at and expires_at > datetime.now(UTC))


def _normalize_pairing_code(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", str(value or "")).upper()


def _pairing_code_hash(value: str) -> str:
    return hashlib.sha256(_normalize_pairing_code(value).encode("ascii")).hexdigest()


def _format_pairing_code(value: str) -> str:
    normalized = _normalize_pairing_code(value)
    return "-".join(normalized[index : index + 4] for index in range(0, len(normalized), 4))


def _normalized_host(value: str) -> str:
    raw = str(value or "").strip()
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    host = str(parsed.hostname or "").lower().rstrip(".")
    return host[4:] if host.startswith("www.") else host


def _canonical_site_url(value: str) -> str:
    raw = str(value or "").strip()
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    host = str(parsed.hostname or "").lower().rstrip(".")
    if not host:
        raise WordPressConnectionError(
            "This business needs a valid website before WordPress can be paired.",
            reason_code="wordpress_site_url_invalid",
            status_code=422,
        )
    scheme = parsed.scheme if parsed.scheme in {"http", "https"} else "https"
    port = f":{parsed.port}" if parsed.port else ""
    path = parsed.path.rstrip("/")
    return f"{scheme}://{host}{port}{path}"


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
