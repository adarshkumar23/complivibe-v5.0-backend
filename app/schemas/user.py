from app.schemas.common import UUIDTimestampSchema


class UserRead(UUIDTimestampSchema):
    email: str
    full_name: str | None = None
    status: str
    is_active: bool
    is_superuser: bool
