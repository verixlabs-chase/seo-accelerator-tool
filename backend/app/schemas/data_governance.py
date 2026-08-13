from uuid import UUID

from pydantic import BaseModel
from typing import Literal


class DataExportCreateIn(BaseModel):
    client_request_id: UUID


class ProviderDisconnectCreateIn(BaseModel):
    client_request_id: UUID
    provider_name: Literal["google"] = "google"
    confirmation: str


class OrganizationClosureCreateIn(BaseModel):
    client_request_id: UUID
    confirmation: str


class OrganizationLegalHoldCreateIn(BaseModel):
    organization_id: UUID
    hold_reference: str
    reason_summary: str
