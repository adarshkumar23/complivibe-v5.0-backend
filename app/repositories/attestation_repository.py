import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.export_attestation import ExportAttestation


class AttestationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_attestation(self, attestation_id: uuid.UUID) -> ExportAttestation | None:
        return self.db.execute(select(ExportAttestation).where(ExportAttestation.id == attestation_id)).scalar_one_or_none()

    def list_for_export(self, organization_id: uuid.UUID, export_job_id: uuid.UUID) -> list[ExportAttestation]:
        stmt = (
            select(ExportAttestation)
            .where(
                ExportAttestation.organization_id == organization_id,
                ExportAttestation.export_job_id == export_job_id,
            )
            .order_by(ExportAttestation.attested_at.desc())
        )
        return self.db.execute(stmt).scalars().all()

    def latest_active_for_export(self, organization_id: uuid.UUID, export_job_id: uuid.UUID) -> ExportAttestation | None:
        stmt = (
            select(ExportAttestation)
            .where(
                ExportAttestation.organization_id == organization_id,
                ExportAttestation.export_job_id == export_job_id,
                ExportAttestation.status == "active",
            )
            .order_by(ExportAttestation.attested_at.desc())
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()
