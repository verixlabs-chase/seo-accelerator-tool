from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class LocalRankGridRequest(BaseModel):
    campaign_id: str = Field(min_length=1, max_length=36)
    keyword_ids: list[str] = Field(min_length=1, max_length=3)
    grid_size: int = 5
    radius_miles: float = Field(default=5, ge=1, le=25)

    @model_validator(mode="after")
    def validate_grid(self) -> "LocalRankGridRequest":
        if self.grid_size not in {3, 5, 7}:
            raise ValueError("grid_size must be 3, 5, or 7")
        if len(self.keyword_ids) != len(set(self.keyword_ids)):
            raise ValueError("Choose each search phrase only once.")
        return self


class LocalRankGridCreateRequest(LocalRankGridRequest):
    idempotency_key: str = Field(min_length=8, max_length=128)
