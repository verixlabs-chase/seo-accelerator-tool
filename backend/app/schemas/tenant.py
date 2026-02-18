from datetime import datetime

from pydantic import BaseModel


class TenantCreateRequest(BaseModel):
    name: str


class TenantStatusTransitionRequest(BaseModel):
    target_status: str


class TenantOut(BaseModel):
    id: str
    name: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}
