import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ai_system import AISystem
from app.models.training_dataset import TrainingDataset
from app.schemas.training_dataset import (
    UNCLEAR_CONSENT_BASES,
    UNCLEAR_LICENSE_TYPES,
    TrainingDatasetCreate,
    TrainingDatasetUpdate,
)
from app.services.audit_service import AuditService

# AI system lifecycle states considered "terminal" (no longer active) for the
# purposes of the training-data rights gap analysis. Systems in these states,
# or with archived_at set, are excluded from the gap report.
TERMINAL_LIFECYCLE_STATUSES = {"archived", "retired"}


class TrainingDatasetService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(UTC)

    def _require_ai_system(self, org_id: uuid.UUID, ai_system_id: uuid.UUID) -> AISystem:
        row = self.db.execute(
            select(AISystem).where(
                AISystem.id == ai_system_id,
                AISystem.organization_id == org_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Linked AI system not found in this organization",
            )
        return row

    def _get(self, org_id: uuid.UUID, dataset_id: uuid.UUID) -> TrainingDataset:
        row = self.db.execute(
            select(TrainingDataset).where(
                TrainingDataset.id == dataset_id,
                TrainingDataset.organization_id == org_id,
                TrainingDataset.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training dataset not found")
        return row

    @staticmethod
    def _snapshot(row: TrainingDataset) -> dict[str, Any]:
        return {
            "name": row.name,
            "source": row.source,
            "license_type": row.license_type,
            "consent_basis": row.consent_basis,
            "linked_ai_system_id": str(row.linked_ai_system_id),
            "record_count": row.record_count,
            "notes": row.notes,
            "rights_status": row.rights_status,
            "rights_expires_at": row.rights_expires_at.isoformat() if row.rights_expires_at else None,
        }

    def list(
        self,
        org_id: uuid.UUID,
        *,
        license_type: str | None = None,
        linked_ai_system_id: uuid.UUID | None = None,
    ) -> list[TrainingDataset]:
        stmt = select(TrainingDataset).where(
            TrainingDataset.organization_id == org_id,
            TrainingDataset.deleted_at.is_(None),
        )
        if license_type is not None:
            stmt = stmt.where(TrainingDataset.license_type == license_type)
        if linked_ai_system_id is not None:
            stmt = stmt.where(TrainingDataset.linked_ai_system_id == linked_ai_system_id)
        stmt = stmt.order_by(TrainingDataset.created_at.desc())
        return list(self.db.execute(stmt).scalars().all())

    def get(self, org_id: uuid.UUID, dataset_id: uuid.UUID) -> TrainingDataset:
        return self._get(org_id, dataset_id)

    def create(
        self,
        org_id: uuid.UUID,
        payload: TrainingDatasetCreate,
        *,
        actor_user_id: uuid.UUID | None,
    ) -> TrainingDataset:
        self._require_ai_system(org_id, payload.linked_ai_system_id)

        row = TrainingDataset(
            organization_id=org_id,
            name=payload.name,
            source=payload.source,
            license_type=payload.license_type,
            consent_basis=payload.consent_basis,
            linked_ai_system_id=payload.linked_ai_system_id,
            record_count=payload.record_count,
            notes=payload.notes,
            rights_status=payload.rights_status,
            rights_expires_at=payload.rights_expires_at,
            created_by=actor_user_id,
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="training_dataset.created",
            entity_type="training_dataset",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            after_json=self._snapshot(row),
        )
        return row

    def update(
        self,
        org_id: uuid.UUID,
        dataset_id: uuid.UUID,
        payload: TrainingDatasetUpdate,
        *,
        actor_user_id: uuid.UUID | None,
    ) -> TrainingDataset:
        row = self._get(org_id, dataset_id)
        before = self._snapshot(row)

        data = payload.model_dump(exclude_unset=True)
        if "linked_ai_system_id" in data and data["linked_ai_system_id"] is not None:
            self._require_ai_system(org_id, data["linked_ai_system_id"])

        for field, value in data.items():
            setattr(row, field, value)

        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="training_dataset.updated",
            entity_type="training_dataset",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            before_json=before,
            after_json=self._snapshot(row),
        )
        return row

    def delete(
        self,
        org_id: uuid.UUID,
        dataset_id: uuid.UUID,
        *,
        actor_user_id: uuid.UUID | None,
    ) -> TrainingDataset:
        row = self._get(org_id, dataset_id)
        before = self._snapshot(row)
        row.deleted_at = self._utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="training_dataset.deleted",
            entity_type="training_dataset",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            before_json=before,
            after_json=self._snapshot(row),
        )
        return row

    @staticmethod
    def _has_clear_provenance(ds: TrainingDataset) -> bool:
        return ds.license_type not in UNCLEAR_LICENSE_TYPES and ds.consent_basis not in UNCLEAR_CONSENT_BASES

    @classmethod
    def _is_currently_documented(cls, ds: TrainingDataset, today: Any) -> bool:
        """A dataset is a valid, currently-defensible rights basis right now."""
        if not cls._has_clear_provenance(ds):
            return False
        if ds.rights_status != "active":
            return False
        if ds.rights_expires_at is not None and ds.rights_expires_at < today:
            return False
        return True

    @classmethod
    def _has_lapsed_rights(cls, ds: TrainingDataset, today: Any) -> bool:
        """A dataset that WAS documented (clear license/consent) but whose rights
        basis has since expired or been revoked, or is past its expiry date."""
        if not cls._has_clear_provenance(ds):
            return False
        if ds.rights_status in ("expired", "revoked"):
            return True
        if ds.rights_expires_at is not None and ds.rights_expires_at < today:
            return True
        return False

    def rights_gaps(self, org_id: uuid.UUID) -> dict[str, Any]:
        """Compute AI training-data rights coverage gaps for an organization.

        Classification per non-archived AI system:
          - no_dataset_linked: zero training_datasets rows reference it.
          - documented: has at least one dataset that is CURRENTLY a valid,
            defensible rights basis, i.e. clear license_type/consent_basis AND
            rights_status == 'active' AND not past its rights_expires_at. This
            is the "any-one-fully-documented-dataset" rule: one solid dataset
            is enough to cover the system.
          - rights_lapsed: has clear license/consent documentation on at least
            one dataset, but that documentation has since expired or been
            revoked (or is past its expiry date) and no OTHER dataset is
            currently valid. This is distinct from "unclear_rights" because it
            flags a system whose training data rights were once established
            but have since lapsed -- a materially different legal-exposure
            signal (a resolved risk that re-opened) than data that was never
            documented at all.
          - unclear_rights: has at least one dataset, but none are currently
            documented and none merely lapsed (i.e. rights were never clearly
            established in the first place).
        """
        today = self._utcnow().date()

        systems = list(
            self.db.execute(
                select(AISystem).where(
                    AISystem.organization_id == org_id,
                    AISystem.archived_at.is_(None),
                    ~AISystem.lifecycle_status.in_(TERMINAL_LIFECYCLE_STATUSES),
                )
            )
            .scalars()
            .all()
        )

        datasets = list(
            self.db.execute(
                select(TrainingDataset).where(
                    TrainingDataset.organization_id == org_id,
                    TrainingDataset.deleted_at.is_(None),
                )
            )
            .scalars()
            .all()
        )

        datasets_by_system: dict[uuid.UUID, list[TrainingDataset]] = {}
        for ds in datasets:
            datasets_by_system.setdefault(ds.linked_ai_system_id, []).append(ds)

        no_dataset_linked: list[AISystem] = []
        unclear_rights: list[AISystem] = []
        rights_lapsed: list[AISystem] = []
        documented: list[AISystem] = []

        for system in systems:
            system_datasets = datasets_by_system.get(system.id, [])
            if not system_datasets:
                no_dataset_linked.append(system)
                continue

            if any(self._is_currently_documented(ds, today) for ds in system_datasets):
                documented.append(system)
            elif any(self._has_lapsed_rights(ds, today) for ds in system_datasets):
                rights_lapsed.append(system)
            else:
                unclear_rights.append(system)

        def _ref(system: AISystem) -> dict[str, Any]:
            return {"id": system.id, "name": system.name}

        return {
            "total_ai_systems": len(systems),
            "documented_count": len(documented),
            "unclear_rights_count": len(unclear_rights),
            "no_dataset_linked_count": len(no_dataset_linked),
            "rights_lapsed_count": len(rights_lapsed),
            "no_dataset_linked": [_ref(s) for s in no_dataset_linked],
            "unclear_rights": [_ref(s) for s in unclear_rights],
            "rights_lapsed": [_ref(s) for s in rights_lapsed],
        }
