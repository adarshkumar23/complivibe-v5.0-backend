from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class CCPAOptOutRequest(BaseModel):
    subject_email: EmailStr
    subject_name: str = Field(min_length=1, max_length=255)
    org_slug: str = Field(min_length=1, max_length=100)


class CCPAOptOutResponse(BaseModel):
    request_ref: str
    response_deadline: datetime
    message: str
