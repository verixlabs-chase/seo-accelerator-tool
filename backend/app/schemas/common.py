from pydantic import BaseModel


class Meta(BaseModel):
    request_id: str
    tenant_id: str | None = None


class ErrorPayload(BaseModel):
    code: str
    message: str
    details: dict = {}


class Envelope(BaseModel):
    data: dict | None
    meta: Meta
    error: ErrorPayload | None = None

