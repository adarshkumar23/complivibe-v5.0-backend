import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CookieCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    domain: str = Field(min_length=1, max_length=500)
    category: str
    purpose: str | None = None
    provider: str | None = Field(default=None, max_length=255)
    duration: str | None = Field(default=None, max_length=100)
    is_third_party: bool = False


class CookieUpdate(BaseModel):
    category: str | None = None
    purpose: str | None = None
    provider: str | None = Field(default=None, max_length=255)
    duration: str | None = Field(default=None, max_length=100)
    is_third_party: bool | None = None
    is_active: bool | None = None


class CookieRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    domain: str
    category: str
    purpose: str | None
    provider: str | None
    duration: str | None
    is_third_party: bool
    last_seen_at: datetime | None
    first_seen_at: datetime | None
    source: str
    is_active: bool
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime


class CookieScanItem(BaseModel):
    name: str
    category: str
    purpose: str | None = None
    provider: str | None = None
    duration: str | None = None
    is_third_party: bool = False


class CookieScanReport(BaseModel):
    domain: str
    cookies: list[CookieScanItem]
    scanned_at: datetime


class CookieScanResult(BaseModel):
    new_cookies: int
    updated: int


class BannerConfigCreate(BaseModel):
    banner_title: str = Field(default="Cookie Preferences", max_length=255)
    banner_body: str
    accept_all_text: str = Field(default="Accept All", max_length=100)
    reject_all_text: str = Field(default="Reject All", max_length=100)
    manage_text: str = Field(default="Manage Preferences", max_length=100)
    enabled_categories: list[str] = Field(default_factory=lambda: ["strictly_necessary", "functional", "analytics", "marketing"])
    is_active: bool = True


class BannerConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    banner_title: str
    banner_body: str
    accept_all_text: str
    reject_all_text: str
    manage_text: str
    enabled_categories: list
    is_active: bool
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime


class PublicBannerRead(BaseModel):
    organization_slug: str
    banner_config: dict
    cookie_categories: list[str]
