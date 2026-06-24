import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.membership import Membership
from app.models.user import User
from app.models.vendor import Vendor


class VendorService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def require_vendor_in_org(self, organization_id: uuid.UUID, vendor_id: uuid.UUID) -> Vendor:
        row = self.db.execute(
            select(Vendor).where(
                Vendor.id == vendor_id,
                Vendor.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor not found")
        return row

    def ensure_owner_is_active_member(self, organization_id: uuid.UUID, owner_user_id: uuid.UUID) -> User:
        membership = self.db.execute(
            select(Membership).where(
                Membership.organization_id == organization_id,
                Membership.user_id == owner_user_id,
                Membership.status == "active",
            )
        ).scalar_one_or_none()
        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="owner_user_id must be an active member of the organization",
            )

        user = self.db.execute(select(User).where(User.id == owner_user_id)).scalar_one_or_none()
        if user is None or not user.is_active or user.status != "active":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="owner_user_id must be an active member of the organization",
            )
        return user

    def summary(self, organization_id: uuid.UUID) -> dict[str, int | dict[str, int]]:
        total_vendors = int(
            self.db.execute(select(func.count(Vendor.id)).where(Vendor.organization_id == organization_id)).scalar_one()
        )
        active_vendors = int(
            self.db.execute(
                select(func.count(Vendor.id)).where(
                    Vendor.organization_id == organization_id,
                    Vendor.status != "archived",
                )
            ).scalar_one()
        )
        archived_vendors = int(
            self.db.execute(
                select(func.count(Vendor.id)).where(
                    Vendor.organization_id == organization_id,
                    Vendor.status == "archived",
                )
            ).scalar_one()
        )

        by_status_rows = self.db.execute(
            select(Vendor.status, func.count(Vendor.id))
            .where(Vendor.organization_id == organization_id)
            .group_by(Vendor.status)
        ).all()
        by_risk_tier_rows = self.db.execute(
            select(Vendor.risk_tier, func.count(Vendor.id))
            .where(Vendor.organization_id == organization_id)
            .group_by(Vendor.risk_tier)
        ).all()
        by_vendor_type_rows = self.db.execute(
            select(Vendor.vendor_type, func.count(Vendor.id))
            .where(Vendor.organization_id == organization_id)
            .group_by(Vendor.vendor_type)
        ).all()

        return {
            "total_vendors": total_vendors,
            "active_vendors": active_vendors,
            "archived_vendors": archived_vendors,
            "by_status": {str(key): int(value) for key, value in by_status_rows},
            "by_risk_tier": {str(key): int(value) for key, value in by_risk_tier_rows},
            "by_vendor_type": {str(key): int(value) for key, value in by_vendor_type_rows},
        }
