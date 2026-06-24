import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.membership import Membership


class MembershipRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_by_organization(self, organization_id: uuid.UUID) -> list[Membership]:
        stmt = (
            select(Membership)
            .where(Membership.organization_id == organization_id)
            .order_by(Membership.created_at.asc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def get_by_id(self, membership_id: uuid.UUID) -> Membership | None:
        stmt = select(Membership).where(Membership.id == membership_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_user_and_org(self, user_id: uuid.UUID, organization_id: uuid.UUID) -> Membership | None:
        stmt = select(Membership).where(
            Membership.user_id == user_id,
            Membership.organization_id == organization_id,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def create(
        self,
        *,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        role_id: uuid.UUID,
        status: str,
        invited_by: uuid.UUID | None,
    ) -> Membership:
        membership = Membership(
            organization_id=organization_id,
            user_id=user_id,
            role_id=role_id,
            status=status,
            invited_by=invited_by,
        )
        self.db.add(membership)
        self.db.flush()
        return membership
