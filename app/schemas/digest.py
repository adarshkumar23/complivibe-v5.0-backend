from datetime import datetime

from pydantic import BaseModel, Field


class DigestConfigRead(BaseModel):
    id: str
    organization_id: str
    user_id: str
    digest_type: str
    is_enabled: bool
    send_time_utc: str
    send_day_of_week: int | None
    last_sent_at: datetime | None


class DigestDailyUpdate(BaseModel):
    is_enabled: bool
    send_time_utc: str = Field(default="08:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")


class DigestWeeklyUpdate(BaseModel):
    is_enabled: bool
    send_day_of_week: int = Field(default=0, ge=0, le=6)
