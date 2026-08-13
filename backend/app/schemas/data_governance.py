from uuid import UUID

from pydantic import BaseModel
from typing import Literal


class DataExportCreateIn(BaseModel):
    client_request_id: UUID


class ProviderDisconnectCreateIn(BaseModel):
    client_request_id: UUID
    provider_name: Literal["google"] = "google"
    confirmation: str
