from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import enforce_organization_scope, require_org_role
from app.api.response import envelope
from app.db.session import get_db
from app.models.business_location import BusinessLocation
from app.models.campaign import Campaign
from app.models.data_connection import DataConnection
from app.services import data_connections_service, durable_job_service


router = APIRouter(tags=["data-connections"])


class SearchConsoleMappingIn(BaseModel):
    external_resource_id: str = Field(..., min_length=1, max_length=500)
    external_resource_name: str | None = Field(default=None, max_length=500)


def _raise_connection_error(exc: data_connections_service.DataConnectionError) -> None:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"message": str(exc), "reason_code": exc.reason_code},
    ) from exc


@router.get("/organizations/{organization_id}/data-connections")
def get_data_connections(
    request: Request,
    organization_id: str,
    user: dict = Depends(require_org_role({"org_user"})),
    db: Session = Depends(get_db),
) -> dict:
    enforce_organization_scope(user=user, organization_id=organization_id, allow_platform=False)
    return envelope(
        request,
        {
            "organization_id": organization_id,
            "google_oauth": data_connections_service.google_oauth_connection_summary(
                db,
                organization_id,
            ),
            "connections": data_connections_service.list_connections(db, organization_id),
            "supported_connections": [
                {
                    "provider_name": data_connections_service.GOOGLE_SEARCH_CONSOLE_PROVIDER,
                    "label": "Google Search Console",
                    "status": "available",
                    "purpose": "Website visibility, clicks, impressions, and average search position.",
                },
                {
                    "provider_name": "google_business_profile",
                    "label": "Google Business Profile",
                    "status": "planned",
                    "purpose": "Business profile, reviews, and local search activity.",
                },
                {
                    "provider_name": "website_analytics",
                    "label": "Website analytics and forms",
                    "status": "planned",
                    "purpose": "Website visits and form-conversion events.",
                },
            ],
        },
    )


@router.get(
    "/organizations/{organization_id}/data-connections/google-search-console/resources"
)
def get_search_console_resources(
    request: Request,
    organization_id: str,
    user: dict = Depends(require_org_role({"org_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    enforce_organization_scope(user=user, organization_id=organization_id, allow_platform=False)
    try:
        resources = data_connections_service.discover_search_console_resources(
            db,
            organization_id,
        )
    except data_connections_service.DataConnectionError as exc:
        _raise_connection_error(exc)
    return envelope(
        request,
        {
            "organization_id": organization_id,
            "provider_name": data_connections_service.GOOGLE_SEARCH_CONSOLE_PROVIDER,
            "resources": resources,
        },
    )


@router.get(
    "/organizations/{organization_id}/data-connections/"
    "google-search-console/metrics/{campaign_id}"
)
def get_search_console_metrics(
    request: Request,
    organization_id: str,
    campaign_id: str,
    days: int = Query(default=90, ge=7, le=480),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    comparison_mode: str = Query(
        default="previous_period",
        pattern="^(previous_period|previous_year|custom|none)$",
    ),
    comparison_date_from: date | None = Query(default=None),
    comparison_date_to: date | None = Query(default=None),
    user: dict = Depends(require_org_role({"org_user"})),
    db: Session = Depends(get_db),
) -> dict:
    enforce_organization_scope(user=user, organization_id=organization_id, allow_platform=False)
    try:
        payload = data_connections_service.get_search_console_metrics(
            db,
            organization_id=organization_id,
            campaign_id=campaign_id,
            days=days,
            date_from=date_from,
            date_to=date_to,
            comparison_mode=comparison_mode,
            comparison_date_from=comparison_date_from,
            comparison_date_to=comparison_date_to,
        )
    except data_connections_service.DataConnectionError as exc:
        _raise_connection_error(exc)
    return envelope(request, payload)


@router.put(
    "/organizations/{organization_id}/data-connections/google-search-console/mappings/{campaign_id}"
)
def map_search_console_resource(
    request: Request,
    organization_id: str,
    campaign_id: str,
    body: SearchConsoleMappingIn,
    user: dict = Depends(require_org_role({"org_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    enforce_organization_scope(user=user, organization_id=organization_id, allow_platform=False)
    try:
        connection = data_connections_service.upsert_search_console_mapping(
            db,
            organization_id=organization_id,
            campaign_id=campaign_id,
            external_resource_id=body.external_resource_id,
            external_resource_name=body.external_resource_name,
            actor_user_id=user["id"],
        )
    except data_connections_service.DataConnectionError as exc:
        _raise_connection_error(exc)
    campaign = db.get(Campaign, connection.campaign_id)
    location = db.get(BusinessLocation, connection.business_location_id)
    return envelope(
        request,
        {
            "connection": data_connections_service.serialize_connection(
                connection,
                campaign=campaign,
                location=location,
            )
        },
    )


@router.post(
    "/organizations/{organization_id}/data-connections/{connection_id}/sync"
)
def sync_data_connection(
    request: Request,
    organization_id: str,
    connection_id: str,
    user: dict = Depends(require_org_role({"org_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    enforce_organization_scope(user=user, organization_id=organization_id, allow_platform=False)
    connection = (
        db.query(DataConnection)
        .filter(
            DataConnection.id == connection_id,
            DataConnection.organization_id == organization_id,
        )
        .first()
    )
    if connection is None:
        raise HTTPException(status_code=404, detail="Data connection not found.")
    if connection.provider_name != data_connections_service.GOOGLE_SEARCH_CONSOLE_PROVIDER:
        raise HTTPException(status_code=400, detail="This connection cannot be synchronized yet.")
    try:
        job = durable_job_service.run_search_console_sync_now(
            db,
            tenant_id=connection.tenant_id,
            organization_id=organization_id,
            connection_id=connection.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.expire_all()
    refreshed = db.get(DataConnection, connection.id)
    campaign = db.get(Campaign, refreshed.campaign_id) if refreshed is not None else None
    location = (
        db.get(BusinessLocation, refreshed.business_location_id)
        if refreshed is not None
        else None
    )
    return envelope(
        request,
        {
            "job": job,
            "connection": (
                data_connections_service.serialize_connection(
                    refreshed,
                    campaign=campaign,
                    location=location,
                )
                if refreshed is not None
                else None
            ),
        },
    )
