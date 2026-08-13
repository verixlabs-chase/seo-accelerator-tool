from uuid import UUID

from pydantic import BaseModel


class DataExportCreateIn(BaseModel):
    client_request_id: UUID
