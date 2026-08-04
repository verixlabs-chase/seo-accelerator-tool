from typing import Literal

from pydantic import BaseModel, Field, field_validator


class BusinessServiceCreateIn(BaseModel):
    campaign_id: str = Field(min_length=1, max_length=36)
    name: str = Field(min_length=1, max_length=160)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Enter a service customers can hire you for.")
        return normalized


class BusinessServiceDiscoverIn(BaseModel):
    campaign_id: str = Field(min_length=1, max_length=36)


class BusinessServicePatchIn(BaseModel):
    campaign_id: str = Field(min_length=1, max_length=36)
    status: Literal["confirmed", "rejected"]
