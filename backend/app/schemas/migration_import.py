from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class MigrationDryRunIn(BaseModel):
    source_system: Literal["semrush", "brightlocal", "other"] = "other"
    csv_text: str = Field(min_length=1, max_length=1_500_000)


class MigrationApplyIn(MigrationDryRunIn):
    review_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    client_request_id: UUID
    source_filename: str | None = Field(default=None, max_length=255)
    confirmed: bool = False


class MigrationRollbackIn(BaseModel):
    confirmed: bool = False
