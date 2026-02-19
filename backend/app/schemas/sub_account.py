from datetime import datetime

from pydantic import BaseModel, Field


class SubAccountCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)


class SubAccountPatchIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    status: str | None = Field(default=None)


class SubAccountOut(BaseModel):
    id: str
    organization_id: str
    name: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
