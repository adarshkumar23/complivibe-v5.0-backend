from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class ExportSettingsUpdate(BaseModel):
    logo_url: str | None = Field(default=None, max_length=500)
    company_display_name: str | None = Field(default=None, max_length=200)
    footer_text: str | None = Field(default=None, max_length=500)
    primary_color_hex: str | None = Field(default=None, max_length=7)

    @field_validator("primary_color_hex")
    @classmethod
    def validate_color(cls, value: str | None) -> str | None:
        if value in (None, ""):
            return None
        if len(value) != 7 or not value.startswith("#"):
            raise ValueError("primary_color_hex must be in format '#RRGGBB'")
        hex_part = value[1:]
        if any(ch not in "0123456789abcdefABCDEF" for ch in hex_part):
            raise ValueError("primary_color_hex must be in format '#RRGGBB'")
        return f"#{hex_part.upper()}"


class ExportSettingsRead(BaseModel):
    id: uuid.UUID | None = None
    organization_id: uuid.UUID
    logo_url: str | None = None
    company_display_name: str | None = None
    footer_text: str | None = None
    primary_color_hex: str | None = None
    is_default: bool = False
    is_stale: bool = False
    context_flags: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None
