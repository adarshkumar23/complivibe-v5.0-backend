import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.data_principal_nomination import DataPrincipalNomination
from app.privacy.services.consent_service import ConsentService
from app.services.audit_service import AuditService
from app.core.validation import validate_choice

ALLOWED_ACTIVATION_TRIGGERS = {"death", "incapacity"}


class NominationService:
    """DPDP Act 2023 Section 10 (DPDP Rules 2025, Rule 10): a Data Principal may
    nominate another individual to exercise their rights on their behalf in the
    event of death or incapacity."""

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def _require_nomination(self, org_id: uuid.UUID, nomination_id: uuid.UUID) -> DataPrincipalNomination:
        row = self.db.execute(
            select(DataPrincipalNomination).where(
                DataPrincipalNomination.organization_id == org_id,
                DataPrincipalNomination.id == nomination_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nomination not found")
        return row

    def create_nomination(
        self,
        org_id: uuid.UUID,
        subject_identifier: str,
        activation_trigger: str,
        nominee_name: str | None = None,
        nominee_contact: str | None = None,
        nominee_user_id: uuid.UUID | None = None,
        actor_user_id: uuid.UUID | None = None,
    ) -> DataPrincipalNomination:
        activation_trigger = validate_choice(activation_trigger, ALLOWED_ACTIVATION_TRIGGERS, "activation_trigger")
        if nominee_user_id is None and not nominee_name:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Either nominee_user_id or nominee_name must be provided",
            )

        now = self.utcnow()
        row = DataPrincipalNomination(
            organization_id=org_id,
            subject_identifier_hash=ConsentService.hash_subject_identifier(subject_identifier),
            nominee_user_id=nominee_user_id,
            nominee_name=nominee_name,
            nominee_contact=nominee_contact,
            activation_trigger=activation_trigger,
            status="active",
            created_by_user_id=actor_user_id,
            created_at=now,
            updated_at=now,
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="dpdp_nomination.created",
            entity_type="data_principal_nomination",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            after_json={"activation_trigger": activation_trigger, "status": row.status},
            metadata_json={"source": "api"},
        )
        return row

    def get_active_nomination(self, org_id: uuid.UUID, subject_identifier: str) -> DataPrincipalNomination | None:
        subject_hash = ConsentService.hash_subject_identifier(subject_identifier)
        return self.db.execute(
            select(DataPrincipalNomination).where(
                DataPrincipalNomination.organization_id == org_id,
                DataPrincipalNomination.subject_identifier_hash == subject_hash,
                DataPrincipalNomination.status == "active",
            )
        ).scalar_one_or_none()

    def activate_nomination(
        self, org_id: uuid.UUID, nomination_id: uuid.UUID, actor_user_id: uuid.UUID | None = None
    ) -> DataPrincipalNomination:
        row = self._require_nomination(org_id, nomination_id)
        if row.status != "active":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Cannot activate nomination in status '{row.status}'",
            )
        now = self.utcnow()
        row.status = "activated"
        row.activated_at = now
        row.updated_at = now
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="dpdp_nomination.activated",
            entity_type="data_principal_nomination",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            after_json={"activated_at": row.activated_at.isoformat()},
            metadata_json={"source": "api", "activation_trigger": row.activation_trigger},
        )
        return row

    def revoke_nomination(
        self, org_id: uuid.UUID, nomination_id: uuid.UUID, reason: str | None = None, actor_user_id: uuid.UUID | None = None
    ) -> DataPrincipalNomination:
        row = self._require_nomination(org_id, nomination_id)
        if row.status == "revoked":
            return row
        now = self.utcnow()
        row.status = "revoked"
        row.revoked_at = now
        row.revocation_reason = reason
        row.updated_at = now
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="dpdp_nomination.revoked",
            entity_type="data_principal_nomination",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            after_json={"revoked_at": row.revoked_at.isoformat(), "reason": reason},
            metadata_json={"source": "api"},
        )
        return row
