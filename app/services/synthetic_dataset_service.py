import importlib
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.synthetic_dataset import SyntheticDataset
from app.services.audit_service import AuditService

GOVERNANCE_GAP_REASON = (
    "Dataset is marked 'validated' but uses privacy_technique='none' -- claiming "
    "privacy-validated status without applying a privacy-preserving technique is a "
    "logical contradiction and should be reviewed by governance."
)


def _load_training_dataset_model() -> Any | None:
    """Best-effort import of TrainingDataset (T4-13), which may not have landed yet.

    SQLAlchemy resolves the source_dataset_id FK by table name string, so this
    import is only needed for the optional in-org existence check below -- it
    is not required for the mapper/FK to function.
    """
    try:
        module = importlib.import_module("app.models.training_dataset")
    except ModuleNotFoundError:
        return None
    return getattr(module, "TrainingDataset", None)


class SyntheticDatasetService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    # -- lookups -----------------------------------------------------------------

    def require_dataset_in_org(self, organization_id: uuid.UUID, dataset_id: uuid.UUID) -> SyntheticDataset:
        row = self.db.execute(
            select(SyntheticDataset).where(
                SyntheticDataset.id == dataset_id,
                SyntheticDataset.organization_id == organization_id,
                SyntheticDataset.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Synthetic dataset not found")
        return row

    def _validate_source_dataset(self, organization_id: uuid.UUID, source_dataset_id: uuid.UUID | None) -> None:
        if source_dataset_id is None:
            return
        training_dataset_model = _load_training_dataset_model()
        if training_dataset_model is None:
            # T4-13 (training_datasets) has not landed in this working tree yet;
            # skip the existence check rather than crash. See BUILDER report.
            return
        row = self.db.execute(
            select(training_dataset_model.id).where(
                training_dataset_model.id == source_dataset_id,
                training_dataset_model.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source training dataset not found")

    # -- governance gap logic ------------------------------------------------------

    @staticmethod
    def _check_governance_contradiction(privacy_technique: str, validation_status: str) -> bool:
        return validation_status == "validated" and privacy_technique == "none"

    @staticmethod
    def _governance_gap_reason(row: SyntheticDataset) -> str | None:
        if row.governance_gap_flag:
            return GOVERNANCE_GAP_REASON
        return None

    def _recompute_gap_flag(self, row: SyntheticDataset) -> bool:
        was_flagged = row.governance_gap_flag
        row.governance_gap_flag = self._check_governance_contradiction(row.privacy_technique, row.validation_status)
        return was_flagged != row.governance_gap_flag

    # -- snapshots / audit ----------------------------------------------------------

    @staticmethod
    def _snapshot(row: SyntheticDataset) -> dict[str, Any]:
        return {
            "name": row.name,
            "generation_method": row.generation_method,
            "source_dataset_id": str(row.source_dataset_id) if row.source_dataset_id else None,
            "privacy_technique": row.privacy_technique,
            "validation_status": row.validation_status,
            "validation_notes": row.validation_notes,
            "governance_gap_flag": row.governance_gap_flag,
        }

    def _write_audit(
        self,
        *,
        action: str,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
        entity_id: uuid.UUID | None = None,
        before_json: dict | None = None,
        after_json: dict | None = None,
        metadata_json: dict | None = None,
    ) -> None:
        AuditService(self.db).write_audit_log(
            action=action,
            entity_type="synthetic_dataset",
            entity_id=entity_id,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            before_json=before_json,
            after_json=after_json,
            metadata_json=metadata_json or {"source": "api"},
        )

    # -- CRUD -----------------------------------------------------------------------

    def create_dataset(
        self,
        *,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
        data: dict[str, Any],
    ) -> SyntheticDataset:
        self._validate_source_dataset(organization_id, data.get("source_dataset_id"))

        row = SyntheticDataset(
            organization_id=organization_id,
            created_by=actor_user_id,
            name=data["name"],
            generation_method=data["generation_method"],
            source_dataset_id=data.get("source_dataset_id"),
            privacy_technique=data.get("privacy_technique", "none"),
            validation_status=data.get("validation_status", "unvalidated"),
            validation_notes=data.get("validation_notes"),
            governance_gap_flag=False,
        )
        self._recompute_gap_flag(row)
        self.db.add(row)
        self.db.flush()

        metadata_json = {"source": "api"}
        if row.governance_gap_flag:
            metadata_json = {
                "source": "api",
                "governance_gap": True,
                "severity": "high",
                "reason": GOVERNANCE_GAP_REASON,
            }
        self._write_audit(
            action="synthetic_dataset.created",
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            entity_id=row.id,
            after_json=self._snapshot(row),
            metadata_json=metadata_json,
        )
        return row

    def list_datasets(
        self,
        organization_id: uuid.UUID,
        *,
        validation_status: str | None = None,
        privacy_technique: str | None = None,
        governance_gap_flag: bool | None = None,
    ) -> list[SyntheticDataset]:
        stmt = select(SyntheticDataset).where(
            SyntheticDataset.organization_id == organization_id,
            SyntheticDataset.deleted_at.is_(None),
        )
        if validation_status is not None:
            stmt = stmt.where(SyntheticDataset.validation_status == validation_status)
        if privacy_technique is not None:
            stmt = stmt.where(SyntheticDataset.privacy_technique == privacy_technique)
        if governance_gap_flag is not None:
            stmt = stmt.where(SyntheticDataset.governance_gap_flag.is_(governance_gap_flag))
        rows = self.db.execute(stmt.order_by(SyntheticDataset.created_at.desc())).scalars().all()
        return list(rows)

    def update_dataset(
        self,
        *,
        organization_id: uuid.UUID,
        dataset_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
        changes: dict[str, Any],
    ) -> SyntheticDataset:
        row = self.require_dataset_in_org(organization_id, dataset_id)
        if "source_dataset_id" in changes:
            self._validate_source_dataset(organization_id, changes["source_dataset_id"])

        before = self._snapshot(row)
        for field, value in changes.items():
            setattr(row, field, value)

        gap_changed = self._recompute_gap_flag(row)
        self.db.flush()

        metadata_json = {"source": "api"}
        if row.governance_gap_flag and gap_changed:
            metadata_json = {
                "source": "api",
                "governance_gap": True,
                "severity": "high",
                "reason": GOVERNANCE_GAP_REASON,
            }
        self._write_audit(
            action="synthetic_dataset.updated",
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            entity_id=row.id,
            before_json=before,
            after_json=self._snapshot(row),
            metadata_json=metadata_json,
        )
        return row

    def set_validation_status(
        self,
        *,
        organization_id: uuid.UUID,
        dataset_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
        new_status: str,
        notes: str | None,
    ) -> SyntheticDataset:
        row = self.require_dataset_in_org(organization_id, dataset_id)
        before = self._snapshot(row)

        row.validation_status = new_status
        if notes is not None:
            row.validation_notes = notes

        contradiction = self._check_governance_contradiction(row.privacy_technique, row.validation_status)
        self._recompute_gap_flag(row)
        self.db.flush()

        metadata_json: dict[str, Any] = {"source": "api", "action": "validate"}
        if contradiction:
            metadata_json.update(
                {
                    "governance_gap": True,
                    "severity": "high",
                    "flag": "logical_contradiction",
                    "reason": GOVERNANCE_GAP_REASON,
                }
            )
        self._write_audit(
            action="synthetic_dataset.validated",
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            entity_id=row.id,
            before_json=before,
            after_json=self._snapshot(row),
            metadata_json=metadata_json,
        )
        return row

    def soft_delete_dataset(
        self,
        *,
        organization_id: uuid.UUID,
        dataset_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
    ) -> SyntheticDataset:
        row = self.require_dataset_in_org(organization_id, dataset_id)
        before = self._snapshot(row)
        row.deleted_at = self.utcnow()
        self.db.flush()
        self._write_audit(
            action="synthetic_dataset.deleted",
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            entity_id=row.id,
            before_json=before,
            after_json=self._snapshot(row),
        )
        return row

    def list_governance_gaps(self, organization_id: uuid.UUID) -> list[SyntheticDataset]:
        stmt = select(SyntheticDataset).where(
            SyntheticDataset.organization_id == organization_id,
            SyntheticDataset.deleted_at.is_(None),
            SyntheticDataset.governance_gap_flag.is_(True),
        )
        rows = self.db.execute(stmt.order_by(SyntheticDataset.created_at.desc())).scalars().all()
        return list(rows)

    def gap_reason(self, row: SyntheticDataset) -> str | None:
        return self._governance_gap_reason(row)
