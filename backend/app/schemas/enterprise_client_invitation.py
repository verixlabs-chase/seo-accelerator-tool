from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator, model_validator


class EnterpriseClientInvitationCreateIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    location_group_id: str = Field(min_length=36, max_length=36)
    expires_in_days: int = Field(default=7, ge=1, le=14)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if (
            len(normalized) > 320
            or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized)
        ):
            raise ValueError("Enter a valid client email")
        return normalized


class EnterpriseClientInvitationRevokeIn(BaseModel):
    expected_version: int = Field(ge=1)


class EnterpriseClientInvitationAcceptIn(BaseModel):
    password: str = Field(min_length=1, max_length=128)
    password_confirmation: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def passwords_match(self):
        if self.password != self.password_confirmation:
            raise ValueError("Passwords do not match")
        return self
