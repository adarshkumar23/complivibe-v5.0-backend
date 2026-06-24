import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.role import Role


class RoleRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_by_organization(self, organization_id: uuid.UUID) -> list[Role]:
        stmt = select(Role).where(Role.organization_id == organization_id).order_by(Role.name.asc())
        return list(self.db.execute(stmt).scalars().all())

    def get_by_id(self, role_id: uuid.UUID) -> Role | None:
        stmt = select(Role).where(Role.id == role_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_name(self, organization_id: uuid.UUID, name: str) -> Role | None:
        stmt = select(Role).where(Role.organization_id == organization_id, Role.name == name)
        return self.db.execute(stmt).scalar_one_or_none()
