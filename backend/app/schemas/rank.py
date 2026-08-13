from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class RankKeywordIn(BaseModel):
    campaign_id: str
    cluster_name: str = Field(default="Core Terms", min_length=1, max_length=120)
    keyword: str = Field(min_length=1, max_length=255)
    location_code: str | None = Field(default=None, max_length=255)

    @field_validator("cluster_name", "keyword")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("location_code")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        normalized = (value or "").strip()
        return normalized or None


class RankKeywordBulkIn(BaseModel):
    campaign_id: str
    cluster_name: str = Field(default="Core Terms", min_length=1, max_length=120)
    keywords: list[str] = Field(min_length=1, max_length=100)
    location_code: str | None = Field(default=None, max_length=255)

    @field_validator("cluster_name")
    @classmethod
    def normalize_cluster_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("keywords")
    @classmethod
    def normalize_keywords(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            keyword = value.strip()
            if not keyword:
                continue
            if len(keyword) > 255:
                raise ValueError("Keywords must be 255 characters or fewer.")
            key = keyword.casefold()
            if key not in seen:
                normalized.append(keyword)
                seen.add(key)
        if not normalized:
            raise ValueError("At least one non-empty keyword is required.")
        return normalized

    @field_validator("location_code")
    @classmethod
    def normalize_optional_location(cls, value: str | None) -> str | None:
        normalized = (value or "").strip()
        return normalized or None


class RankScheduleIn(BaseModel):
    campaign_id: str
    location_code: str | None = Field(default=None, max_length=255)


class RankingSnapshotOut(BaseModel):
    id: str
    tenant_id: str
    campaign_id: str
    keyword_id: str
    position: int
    confidence: float
    captured_at: datetime
    month_partition: str
    source_type: str = "live_collection"
    source_system: str | None = None
    source_record_id: str | None = None
    import_batch_id: str | None = None

    model_config = {"from_attributes": True}
