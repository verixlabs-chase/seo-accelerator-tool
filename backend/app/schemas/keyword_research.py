from pydantic import BaseModel, ConfigDict, Field, field_validator


class KeywordResearchDiscoverIn(BaseModel):
    campaign_id: str = Field(min_length=1, max_length=36)
    max_suggestions: int = Field(default=75, ge=10, le=100)


class KeywordResearchTrackIn(BaseModel):
    campaign_id: str = Field(min_length=1, max_length=36)
    suggestion_ids: list[str] = Field(min_length=1, max_length=100)

    @field_validator("suggestion_ids")
    @classmethod
    def normalize_ids(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values if value.strip()]
        unique = list(dict.fromkeys(normalized))
        if not unique:
            raise ValueError("Choose at least one search to track.")
        return unique


class KeywordResearchAIReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    campaign_id: str = Field(min_length=1, max_length=36)
    max_items: int = Field(default=8, ge=1, le=12)
    retry_failed: bool = False
