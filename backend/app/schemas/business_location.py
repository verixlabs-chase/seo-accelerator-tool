from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints


NonBlankBusinessLocationName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=255),
]


class BusinessLocationCreateIn(BaseModel):
    name: NonBlankBusinessLocationName
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
