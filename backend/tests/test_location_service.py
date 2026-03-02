from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.services.location_service import LocationWriteService


WRITE_SERVICE = LocationWriteService()


def _insert_sub_account(db_session, organization_id: str, name: str) -> str:
    sub_account_id = str(uuid.uuid4())
    now = datetime.now(UTC)
    db_session.execute(
        text(
            """
            INSERT INTO sub_accounts (
                id,
                organization_id,
                name,
                status,
                created_at,
                updated_at
            ) VALUES (
                :id,
                :organization_id,
                :name,
                :status,
                :created_at,
                :updated_at
            )
            """
        ),
        {
            "id": sub_account_id,
            "organization_id": organization_id,
            "name": name,
            "status": "active",
            "created_at": now,
            "updated_at": now,
        },
    )
    db_session.commit()
    return sub_account_id


def _insert_business_location(db_session, organization_id: str, name: str) -> str:
    business_location_id = str(uuid.uuid4())
    now = datetime.now(UTC)
    db_session.execute(
        text(
            """
            INSERT INTO business_locations (
                id,
                organization_id,
                name,
                domain,
                primary_city,
                status,
                created_at,
                updated_at
            ) VALUES (
                :id,
                :organization_id,
                :name,
                :domain,
                :primary_city,
                :status,
                :created_at,
                :updated_at
            )
            """
        ),
        {
            "id": business_location_id,
            "organization_id": organization_id,
            "name": name,
            "domain": None,
            "primary_city": None,
            "status": "active",
            "created_at": now,
            "updated_at": now,
        },
    )
    db_session.commit()
    return business_location_id


def test_create_location_rejects_cross_org_business_location(db_session) -> None:
    org_a = db_session.execute(text("SELECT id FROM organizations ORDER BY id ASC LIMIT 1")).scalar_one()
    org_b = db_session.execute(text("SELECT id FROM organizations ORDER BY id ASC LIMIT 1 OFFSET 1")).scalar_one()
    sub_account_id = _insert_sub_account(db_session, org_a, "A SubAccount")
    business_location_id = _insert_business_location(db_session, org_b, "Other Org BL")

    with pytest.raises(HTTPException) as exc_info:
        WRITE_SERVICE.create_location(
            db_session,
            organization_id=org_a,
            sub_account_id=sub_account_id,
            location_code="AUS-1",
            name="Austin",
            country_code="US",
            business_location_id=business_location_id,
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["reason_code"] == "business_location_org_mismatch"

    location_count = db_session.execute(
        text(
            """
            SELECT count(*)
            FROM locations
            WHERE organization_id = :organization_id
              AND location_code = :location_code
            """
        ),
        {"organization_id": org_a, "location_code": "AUS-1"},
    ).scalar_one()
    assert location_count == 0


def test_update_location_allows_same_org_business_location_link(db_session) -> None:
    org_id = db_session.execute(text("SELECT id FROM organizations ORDER BY id ASC LIMIT 1")).scalar_one()
    sub_account_id = _insert_sub_account(db_session, org_id, "Primary SubAccount")
    business_location_id = _insert_business_location(db_session, org_id, "Primary BL")

    created = WRITE_SERVICE.create_location(
        db_session,
        organization_id=org_id,
        sub_account_id=sub_account_id,
        location_code="NYC-1",
        name="New York",
        country_code="US",
        business_location_id=None,
    )
    db_session.commit()

    updated = WRITE_SERVICE.update_location(
        db_session,
        location_id=str(created["id"]),
        organization_id=org_id,
        business_location_id=business_location_id,
    )
    db_session.commit()

    assert updated["business_location_id"] == business_location_id

    linked_business_location_id = db_session.execute(
        text(
            """
            SELECT business_location_id
            FROM locations
            WHERE id = :location_id
            """
        ),
        {"location_id": created["id"]},
    ).scalar_one()
    assert linked_business_location_id == business_location_id
