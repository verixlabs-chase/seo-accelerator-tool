from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


AreaType = Literal["city", "postal_code", "county", "radius"]
AreaRelationship = Literal["included", "excluded"]


class BusinessServiceAreaCreateIn(BaseModel):
    campaign_id: str = Field(min_length=1, max_length=36)
    area_type: AreaType
    name: str | None = Field(default=None, max_length=160)
    region: str | None = Field(default=None, max_length=120)
    country_code: str = Field(default="US", min_length=2, max_length=2)
    radius_miles: float | None = Field(default=None, gt=0, le=250)
    relationship: AreaRelationship = "included"

    @field_validator("name", "region")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None

    @model_validator(mode="after")
    def validate_area_value(self) -> "BusinessServiceAreaCreateIn":
        if self.area_type == "radius" and self.radius_miles is None:
            raise ValueError("Enter how many miles this location serves.")
        if self.area_type != "radius" and not self.name:
            raise ValueError("Enter the city, ZIP code, or county.")
        return self


class BusinessServiceAreaSuggestIn(BaseModel):
    campaign_id: str = Field(min_length=1, max_length=36)


class BusinessServiceAreaNearbyIn(BaseModel):
    campaign_id: str = Field(min_length=1, max_length=36)
    radius_miles: float = Field(default=25, ge=1, le=75)


class ServiceBoundaryPoint(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class BusinessServiceAreaBoundaryIn(BaseModel):
    campaign_id: str = Field(min_length=1, max_length=36)
    points: list[ServiceBoundaryPoint] = Field(min_length=3, max_length=24)


class BusinessServiceAreaPatchIn(BaseModel):
    campaign_id: str = Field(min_length=1, max_length=36)
    status: Literal["confirmed", "rejected"]
