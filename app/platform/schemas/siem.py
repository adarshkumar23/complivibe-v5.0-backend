from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


ExportFormat = Literal["json", "cef", "leef", "splunk_hec"]
DeliveryMethod = Literal["webhook", "syslog", "file", "api_pull"]


class SiemConfigCreate(BaseModel):
    export_format: ExportFormat = "json"
    # "webhook": events are pushed via HTTP POST to endpoint_url every time a batch is
    #   exported (POST /siem/export) -- requires endpoint_url.
    # "api_pull": no push happens; the SIEM is expected to poll POST /siem/export itself.
    # "syslog" / "file" are accepted by the schema for forward-compatibility but are NOT
    #   YET IMPLEMENTED -- creating/updating a config with one of these is rejected with a
    #   422 rather than silently accepting a delivery method nothing will ever honor.
    delivery_method: DeliveryMethod = "webhook"
    endpoint_url: str | None = Field(
        default=None,
        description="Required (and must be a public http(s) URL) when delivery_method='webhook'; ignored for 'api_pull'.",
    )
    api_key: str | None = None
    include_actions: list[str] = Field(default_factory=list)
    exclude_actions: list[str] = Field(default_factory=list)
    batch_size: int = Field(default=100, ge=1, le=10000)


class SiemConfigUpdate(BaseModel):
    export_format: ExportFormat | None = None
    delivery_method: DeliveryMethod | None = None
    endpoint_url: str | None = Field(
        default=None,
        description="Required (and must be a public http(s) URL) when delivery_method='webhook'; ignored for 'api_pull'.",
    )
    api_key: str | None = None
    include_actions: list[str] | None = None
    exclude_actions: list[str] | None = None
    batch_size: int | None = Field(default=None, ge=1, le=10000)


class SiemConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    export_format: str
    delivery_method: str
    endpoint_url: str | None
    is_active: bool
    include_actions: list
    exclude_actions: list
    batch_size: int
    last_exported_at: datetime | None
    export_failures: int


class SiemExportRequest(BaseModel):
    limit: int | None = Field(default=None, ge=1, le=10000)
    since_id: uuid.UUID | None = None


class SiemExportResponse(BaseModel):
    records: int
    payload: list | str | None
    cursor: str | None
    has_more: bool
    format: str
    push_delivered: bool = False
    push_error: str | None = None
