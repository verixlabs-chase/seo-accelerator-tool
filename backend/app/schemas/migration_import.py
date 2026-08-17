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


class MigrationUploadCreateIn(BaseModel):
    source_system: Literal["semrush", "brightlocal", "other"] = "other"
    source_filename: str | None = Field(default=None, max_length=255)
    total_chunks: int = Field(ge=1, le=100)
    expected_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    client_request_id: UUID


class MigrationUploadChunkIn(BaseModel):
    content: str = Field(min_length=1, max_length=750_000)
    chunk_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class MigrationUploadApplyIn(BaseModel):
    review_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    client_request_id: UUID
    confirmed: bool = False
