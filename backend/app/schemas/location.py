from datetime import datetime
from typing import Annotated, Optional

from pydantic import BaseModel, Field, StringConstraints


NonBlankLocationName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=160),
]


class LocationCreateIn(BaseModel):
    name: NonBlankLocationName
    business_location_id: str | None = Field(default=None, max_length=36)


class LocationUpdateRequest(BaseModel):
    name: Optional[NonBlankLocationName] = None
    business_location_id: Optional[str] = Field(default=None, max_length=36)


class LocationOut(BaseModel):
    id: str
    organization_id: str
    name: str
    business_location_id: str | None
    created_at: datetime
    updated_at: datetime
