from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints


NonBlankBusinessLocationName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=255),
]


class BusinessLocationCreateIn(BaseModel):
    name: NonBlankBusinessLocationName
    sub_account_id: str | None = Field(default=None, max_length=36)
    domain: str | None = Field(default=None, max_length=255)
    primary_city: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=120)
    region: str | None = Field(default=None, max_length=120)
    country_code: str = Field(default="US", min_length=2, max_length=2)
    address_line1: str | None = Field(default=None, max_length=255)
    postal_code: str | None = Field(default=None, max_length=32)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class BusinessLocationPatchIn(BaseModel):
    name: NonBlankBusinessLocationName | None = None
    sub_account_id: str | None = Field(default=None, max_length=36)
    domain: str | None = Field(default=None, max_length=255)
    primary_city: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=120)
    region: str | None = Field(default=None, max_length=120)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    address_line1: str | None = Field(default=None, max_length=255)
    postal_code: str | None = Field(default=None, max_length=32)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    status: str | None = Field(default=None, max_length=50)


class BusinessLocationOut(BaseModel):
    id: str
    organization_id: str
    sub_account_id: str | None
    name: str
    domain: str | None
    primary_city: str | None
    city: str | None
    region: str | None
    country_code: str
    address_line1: str | None
    postal_code: str | None
    latitude: float | None
    longitude: float | None
    coordinate_precision: str | None
    coordinate_source: str | None
    provider_location_code: str | None
    provider_location_name: str | None
    provider_location_type: str | None
    provider_location_resolved_at: datetime | None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
