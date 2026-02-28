from datetime import datetime

from pydantic import BaseModel, Field


class BusinessLocationCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    domain: str | None = Field(default=None, max_length=255)
    primary_city: str | None = Field(default=None, max_length=255)


class BusinessLocationOut(BaseModel):
    id: str
    organization_id: str
    name: str
    domain: str | None
    primary_city: str | None
    status: str
    created_at: datetime
    updated_at: datetime
