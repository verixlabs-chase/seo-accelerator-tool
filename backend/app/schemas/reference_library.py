from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ReferenceLibraryValidateIn(BaseModel):
    version: str
    artifacts: dict[str, Any] | None = None
    strict_mode: bool = True


class ReferenceLibraryActivateIn(BaseModel):
    version: str
    reason: str | None = None


class ReferenceLibraryVersionOut(BaseModel):
    version: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReferenceLibraryValidationOut(BaseModel):
    validation_run_id: str
    status: str
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ReferenceLibraryActivationOut(BaseModel):
    activation_id: str
    version: str
    status: str


class ReferenceLibraryActiveOut(BaseModel):
    version: str
    activated_at: datetime
    activated_by: str | None = None
