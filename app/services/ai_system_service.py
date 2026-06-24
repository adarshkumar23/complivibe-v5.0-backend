import uuid
import hashlib
import hmac
import json

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.ai_system import AISystem
from app.models.control import Control
from app.models.evidence_item import EvidenceItem
from app.models.membership import Membership
from app.models.risk import Risk
from app.models.role import Role


class AISystemService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def require_ai_system_in_org(self, organization_id: uuid.UUID, ai_system_id: uuid.UUID) -> AISystem:
        row = self.db.execute(
            select(AISystem).where(AISystem.id == ai_system_id, AISystem.organization_id == organization_id)
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI system not found")
        return row

    @staticmethod
    def canonical_json(payload: dict) -> str:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)

    @classmethod
    def sha256_hexdigest(cls, payload: dict) -> str:
        return hashlib.sha256(cls.canonical_json(payload).encode("utf-8")).hexdigest()

    @staticmethod
    def hmac_signature(checksum_sha256: str) -> str:
        secret = get_settings().SECRET_KEY.encode("utf-8")
        return hmac.new(secret, checksum_sha256.encode("utf-8"), hashlib.sha256).hexdigest()

    def ensure_ai_system_linkable(self, row: AISystem) -> None:
        if row.lifecycle_status == "archived":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived AI systems cannot accept new links")

    def ensure_owner_is_active_member(
        self,
        organization_id: uuid.UUID,
        owner_user_id: uuid.UUID | None,
        *,
        field_name: str,
    ) -> None:
        if owner_user_id is None:
            return

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
                detail=f"{field_name} must be an active member of the organization",
            )

    def ensure_active_member(self, organization_id: uuid.UUID, user_id: uuid.UUID | None, *, field_name: str) -> None:
        self.ensure_owner_is_active_member(organization_id, user_id, field_name=field_name)

    def signer_role_name(self, organization_id: uuid.UUID, signer_user_id: uuid.UUID) -> str | None:
        membership = self.db.execute(
            select(Membership).where(
                Membership.organization_id == organization_id,
                Membership.user_id == signer_user_id,
                Membership.status == "active",
            )
        ).scalar_one_or_none()
        if membership is None:
            return None
        role = self.db.execute(select(Role).where(Role.id == membership.role_id)).scalar_one_or_none()
        return role.name if role is not None else None

    def validate_owners(
        self,
        organization_id: uuid.UUID,
        *,
        business_owner_user_id: uuid.UUID | None,
        technical_owner_user_id: uuid.UUID | None,
    ) -> None:
        self.ensure_owner_is_active_member(
            organization_id,
            business_owner_user_id,
            field_name="business_owner_user_id",
        )
        self.ensure_owner_is_active_member(
            organization_id,
            technical_owner_user_id,
            field_name="technical_owner_user_id",
        )

    def require_control_in_org(self, organization_id: uuid.UUID, control_id: uuid.UUID) -> Control:
        control = self.db.execute(
            select(Control).where(Control.id == control_id, Control.organization_id == organization_id)
        ).scalar_one_or_none()
        if control is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Control not found")
        return control

    def require_evidence_in_org(self, organization_id: uuid.UUID, evidence_id: uuid.UUID) -> EvidenceItem:
        evidence = self.db.execute(
            select(EvidenceItem).where(EvidenceItem.id == evidence_id, EvidenceItem.organization_id == organization_id)
        ).scalar_one_or_none()
        if evidence is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence not found")
        return evidence

    def require_risk_in_org(self, organization_id: uuid.UUID, risk_id: uuid.UUID) -> Risk:
        risk = self.db.execute(
            select(Risk).where(Risk.id == risk_id, Risk.organization_id == organization_id)
        ).scalar_one_or_none()
        if risk is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Risk not found")
        return risk

    def summary(self, organization_id: uuid.UUID) -> dict[str, int | dict[str, int]]:
        total_systems = int(
            self.db.execute(select(func.count(AISystem.id)).where(AISystem.organization_id == organization_id)).scalar_one()
        )
        archived_systems = int(
            self.db.execute(
                select(func.count(AISystem.id)).where(
                    AISystem.organization_id == organization_id,
                    AISystem.lifecycle_status == "archived",
                )
            ).scalar_one()
        )
        active_systems = max(0, total_systems - archived_systems)

        lifecycle_rows = self.db.execute(
            select(AISystem.lifecycle_status, func.count(AISystem.id))
            .where(AISystem.organization_id == organization_id)
            .group_by(AISystem.lifecycle_status)
        ).all()
        by_lifecycle_status = {str(status): int(count) for status, count in lifecycle_rows}

        type_rows = self.db.execute(
            select(AISystem.system_type, func.count(AISystem.id))
            .where(AISystem.organization_id == organization_id)
            .group_by(AISystem.system_type)
        ).all()
        by_system_type = {str(system_type): int(count) for system_type, count in type_rows}

        with_business_owner = int(
            self.db.execute(
                select(func.count(AISystem.id)).where(
                    AISystem.organization_id == organization_id,
                    AISystem.business_owner_user_id.is_not(None),
                )
            ).scalar_one()
        )
        with_technical_owner = int(
            self.db.execute(
                select(func.count(AISystem.id)).where(
                    AISystem.organization_id == organization_id,
                    AISystem.technical_owner_user_id.is_not(None),
                )
            ).scalar_one()
        )
        missing_owner_count = int(
            self.db.execute(
                select(func.count(AISystem.id)).where(
                    AISystem.organization_id == organization_id,
                    AISystem.business_owner_user_id.is_(None),
                    AISystem.technical_owner_user_id.is_(None),
                )
            ).scalar_one()
        )

        return {
            "total_systems": total_systems,
            "active_systems": active_systems,
            "archived_systems": archived_systems,
            "by_lifecycle_status": by_lifecycle_status,
            "by_system_type": by_system_type,
            "with_business_owner": with_business_owner,
            "with_technical_owner": with_technical_owner,
            "missing_owner_count": missing_owner_count,
        }
