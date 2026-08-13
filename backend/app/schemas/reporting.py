from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class ReportGenerateIn(BaseModel):
    campaign_id: str
    month_number: int


class ReportDeliverIn(BaseModel):
    recipient: str

    @field_validator("recipient")
    @classmethod
    def validate_recipient(cls, value: str) -> str:
        normalized = value.strip().lower()
        if (
            len(normalized) > 320
            or "@" not in normalized
            or normalized.startswith("@")
            or normalized.endswith("@")
        ):
            raise ValueError("Enter a valid recipient email")
        return normalized


class ReportOut(BaseModel):
    id: str
    tenant_id: str
    campaign_id: str
    month_number: int
    report_status: str
    summary_json: str
    generated_at: datetime

    model_config = {"from_attributes": True}


class ReportScheduleUpsertIn(BaseModel):
    campaign_id: str
    cadence: str
    timezone: str
    next_run_at: datetime
    enabled: bool = True

    @field_validator("cadence")
    @classmethod
    def validate_cadence(cls, value: str) -> str:
        allowed = {"daily", "weekly", "monthly"}
        if value not in allowed:
            raise ValueError("cadence must be one of: daily, weekly, monthly")
        return value


class ReportDeliveryEventOut(BaseModel):
    id: str
    delivery_channel: str
    delivery_status: str
    recipient: str
    provider_message_id: str | None = None
    attempt_number: int = 1
    failure_reason: str | None = None
    sent_at: datetime | None
    delivered_at: datetime | None = None
    opened_at: datetime | None = None
    failed_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ReportArtifactOut(BaseModel):
    id: str
    artifact_type: str
    storage_path: str
    storage_mode: str
    ready: bool
    retrievable: bool
    durable: bool
    content_type: str | None = None
    byte_size: int | None = None
    checksum_sha256: str | None = None
    reason: str | None
    created_at: datetime


class ReportScheduleOut(BaseModel):
    id: str
    tenant_id: str
    campaign_id: str
    cadence: str
    timezone: str
    next_run_at: datetime
    enabled: bool
    retry_count: int
    last_status: str

    model_config = {"from_attributes": True}


class ReportRecipientUpsertIn(BaseModel):
    campaign_id: str
    email: str
    display_name: str | None = Field(default=None, max_length=160)
    recipient_role: str = "owner"
    enabled: bool = True

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if len(normalized) > 320 or "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("Enter a valid recipient email")
        return normalized

    @field_validator("recipient_role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        allowed = {"owner", "manager", "client"}
        if value not in allowed:
            raise ValueError("recipient_role must be one of: owner, manager, client")
        return value


class ReportRecipientOut(BaseModel):
    id: str
    campaign_id: str
    email: str
    display_name: str | None
    recipient_role: str
    enabled: bool
    source_type: str
    source_system: str | None
    source_record_id: str | None
    import_batch_id: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReportShareLinkCreateIn(BaseModel):
    expires_in_hours: int = Field(default=168, ge=1, le=720)


class ReportShareLinkOut(BaseModel):
    id: str
    report_id: str
    expires_at: datetime
    revoked_at: datetime | None
    last_opened_at: datetime | None
    open_count: int
    created_at: datetime
    status: str
    share_url: str | None = None
