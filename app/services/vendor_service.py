import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.membership import Membership
from app.models.user import User
from app.models.vendor import Vendor
from app.models.vendor_assessment import VendorAssessment
from app.models.vendor_mitigation_case import VendorMitigationCase


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
            # Distinguish "doesn't exist at all" (404) from "exists, but belongs to
            # a different organization" (403) -- a cross-tenant lookup (e.g. a
            # spoofed X-Organization-ID header naming a vendor_id that belongs to
            # another org) should be denied the same way every other entity in
            # this codebase denies it, not fall through to a plain 404.
            exists_elsewhere = self.db.execute(select(Vendor.id).where(Vendor.id == vendor_id)).scalar_one_or_none()
            if exists_elsewhere is not None:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Vendor does not belong to this organization")
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

    def ensure_unique_vendor_name(
        self, organization_id: uuid.UUID, name: str, exclude_id: uuid.UUID | None = None
    ) -> None:
        stmt = select(Vendor).where(
            Vendor.organization_id == organization_id,
            func.lower(Vendor.name) == name.strip().lower(),
            Vendor.status != "archived",
        )
        if exclude_id is not None:
            stmt = stmt.where(Vendor.id != exclude_id)
        existing = self.db.execute(stmt).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Vendor name already exists in organization",
            )

    def check_archive_eligibility(self, organization_id: uuid.UUID, vendor_id: uuid.UUID) -> dict:
        active_assessments = int(
            self.db.execute(
                select(func.count(VendorAssessment.id)).where(
                    VendorAssessment.organization_id == organization_id,
                    VendorAssessment.vendor_id == vendor_id,
                    VendorAssessment.status.not_in(["completed", "cancelled"]),
                )
            ).scalar_one()
        )
        open_mitigation_cases = int(
            self.db.execute(
                select(func.count(VendorMitigationCase.id)).where(
                    VendorMitigationCase.organization_id == organization_id,
                    VendorMitigationCase.vendor_id == vendor_id,
                    VendorMitigationCase.deleted_at.is_(None),
                    VendorMitigationCase.status.not_in(["closed", "cancelled"]),
                )
            ).scalar_one()
        )
        if active_assessments > 0 or open_mitigation_cases > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Cannot archive vendor with {active_assessments} active assessment(s) "
                    f"and {open_mitigation_cases} open mitigation case(s); resolve or cancel them first"
                ),
            )
        return {"active_assessments": active_assessments, "open_mitigation_cases": open_mitigation_cases}
