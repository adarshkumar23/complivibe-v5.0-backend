import importlib
import math
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

# Minimum/maximum privacy-parameter thresholds below/above which a technique is
# considered too weak to defensibly support a 'validated' status. Two tiers:
# STANDARD applies by default; STRICT applies when the synthetic dataset's
# source training dataset is linked to an AI system classified as
# high/prohibited risk under the org's EU-AI-Act-style risk_tier -- higher-risk
# AI systems warrant a materially stronger anonymization bar before the
# synthetic data feeding them can be signed off as privacy-validated.
#
# k-anonymity: max re-identification probability is bounded by 1/k (Samarati &
# Sweeney, 1998 k-anonymity model). k>=5 is a commonly-cited regulatory floor
# (e.g. HIPAA expert-determination practice); we require k>=10 for high-risk
# AI systems.
# Differential privacy: for eps-DP, the worst-case membership-inference
# attacker's success probability is bounded by e^eps/(1+e^eps) (Dwork et al.;
# Yeom et al. 2018 membership-inference bound). eps<=10 is a widely-used
# "still offers some protection" ceiling; eps<=1 is the stricter bar commonly
# recommended for meaningful protection, which we require for high-risk AI
# systems.
STANDARD_MIN_K = 5
STANDARD_MAX_EPSILON = 10.0
STRICT_MIN_K = 10
STRICT_MAX_EPSILON = 1.0

HIGH_RISK_AI_TIERS = {"high", "prohibited", "unacceptable"}


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


def _load_ai_system_model() -> Any | None:
    try:
        module = importlib.import_module("app.models.ai_system")
    except ModuleNotFoundError:
        return None
    return getattr(module, "AISystem", None)


def compute_reidentification_risk_score(privacy_technique: str, privacy_parameter: float | None) -> float | None:
    """Estimate worst-case re-identification / membership-inference risk in [0, 1].

    - 'none': no protection applied -> maximal risk (1.0), regardless of parameter.
    - 'k_anonymity': risk bounded by 1/k. None/invalid parameter -> unknown (None).
    - 'differential_privacy': risk bounded by e^eps/(1+e^eps). None/invalid -> unknown (None).
    """
    if privacy_technique == "none":
        return 1.0
    if privacy_parameter is None or privacy_parameter <= 0:
        return None
    if privacy_technique == "k_anonymity":
        return round(min(1.0, 1.0 / privacy_parameter), 6)
    if privacy_technique == "differential_privacy":
        exp_eps = math.exp(min(privacy_parameter, 700))  # avoid overflow for extreme inputs
        return round(exp_eps / (1.0 + exp_eps), 6)
    return None


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

    def _consuming_ai_system_risk_tier(
        self, organization_id: uuid.UUID, source_dataset_id: uuid.UUID | None
    ) -> str | None:
        """Resolve the risk_tier of the AI system that consumes this synthetic
        dataset's source training dataset, if any -- this is what makes the
        governance-gap logic below context-aware of AI system risk elsewhere
        in the platform rather than judging privacy_technique in isolation.
        """
        if source_dataset_id is None:
            return None
        training_dataset_model = _load_training_dataset_model()
        ai_system_model = _load_ai_system_model()
        if training_dataset_model is None or ai_system_model is None:
            return None
        linked_ai_system_id = self.db.execute(
            select(training_dataset_model.linked_ai_system_id).where(
                training_dataset_model.id == source_dataset_id,
                training_dataset_model.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if linked_ai_system_id is None:
            return None
        return self.db.execute(
            select(ai_system_model.risk_tier).where(
                ai_system_model.id == linked_ai_system_id,
                ai_system_model.organization_id == organization_id,
            )
        ).scalar_one_or_none()

    @staticmethod
    def _validate_parameter_consistency(privacy_technique: str, privacy_parameter: float | None) -> None:
        if privacy_technique == "none" and privacy_parameter is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="privacy_parameter is only applicable when privacy_technique is "
                "'differential_privacy' (epsilon) or 'k_anonymity' (k) -- it must be omitted "
                "when privacy_technique is 'none'.",
            )

    # -- governance gap logic ------------------------------------------------------

    @staticmethod
    def _weak_parameter_reason(
        privacy_technique: str, privacy_parameter: float | None, risk_score: float | None, *, strict: bool
    ) -> str | None:
        """Return a specific reason string if the quantified privacy_parameter is
        too weak (or missing) to defensibly support 'validated', else None."""
        if privacy_technique not in ("k_anonymity", "differential_privacy"):
            return None
        if privacy_parameter is None:
            return (
                f"Dataset validated with privacy_technique='{privacy_technique}' but no "
                "privacy_parameter (k or epsilon) was recorded, so re-identification risk "
                "cannot be quantified."
            )
        if privacy_technique == "k_anonymity":
            min_k = STRICT_MIN_K if strict else STANDARD_MIN_K
            if privacy_parameter < min_k:
                context = " (source data feeds a high-risk-classified AI system)" if strict else ""
                return (
                    f"Dataset validated with k_anonymity but k={privacy_parameter:g} is below the "
                    f"minimum threshold of {min_k}{context} -- estimated re-identification risk is "
                    f"{risk_score:.0%}, too weak to support a 'validated' status."
                )
        if privacy_technique == "differential_privacy":
            max_eps = STRICT_MAX_EPSILON if strict else STANDARD_MAX_EPSILON
            if privacy_parameter > max_eps:
                context = " (source data feeds a high-risk-classified AI system)" if strict else ""
                return (
                    f"Dataset validated with differential_privacy but epsilon={privacy_parameter:g} exceeds "
                    f"the maximum threshold of {max_eps:g}{context} -- estimated membership-inference risk is "
                    f"{risk_score:.0%}, too weak to support a 'validated' status."
                )
        return None

    def _evaluate_gap(self, row: SyntheticDataset, *, strict: bool) -> tuple[bool, str | None]:
        if row.validation_status != "validated":
            return False, None
        if row.privacy_technique == "none":
            return True, GOVERNANCE_GAP_REASON
        weak_reason = self._weak_parameter_reason(
            row.privacy_technique, row.privacy_parameter, row.reidentification_risk_score, strict=strict
        )
        if weak_reason is not None:
            return True, weak_reason
        return False, None

    def _recompute_gap_flag(self, row: SyntheticDataset, organization_id: uuid.UUID) -> bool:
        row.reidentification_risk_score = compute_reidentification_risk_score(
            row.privacy_technique, row.privacy_parameter
        )
        strict = self._consuming_ai_system_risk_tier(organization_id, row.source_dataset_id) in HIGH_RISK_AI_TIERS
        was_flagged = row.governance_gap_flag
        flagged, reason = self._evaluate_gap(row, strict=strict)
        row.governance_gap_flag = flagged
        row._governance_gap_reason_cache = reason  # noqa: SLF001 -- transient, not persisted
        return was_flagged != row.governance_gap_flag

    def gap_reason(self, row: SyntheticDataset) -> str | None:
        cached = getattr(row, "_governance_gap_reason_cache", None)
        if cached is not None:
            return cached
        # Fallback for rows fetched without a recompute in this request (e.g.
        # plain GET/list): re-derive deterministically from persisted fields.
        if not row.governance_gap_flag:
            return None
        if row.privacy_technique == "none":
            return GOVERNANCE_GAP_REASON
        strict = self._consuming_ai_system_risk_tier(row.organization_id, row.source_dataset_id) in HIGH_RISK_AI_TIERS
        return self._weak_parameter_reason(
            row.privacy_technique, row.privacy_parameter, row.reidentification_risk_score, strict=strict
        )

    # -- snapshots / audit ----------------------------------------------------------

    @staticmethod
    def _snapshot(row: SyntheticDataset) -> dict[str, Any]:
        return {
            "name": row.name,
            "generation_method": row.generation_method,
            "source_dataset_id": str(row.source_dataset_id) if row.source_dataset_id else None,
            "privacy_technique": row.privacy_technique,
            "privacy_parameter": row.privacy_parameter,
            "reidentification_risk_score": row.reidentification_risk_score,
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
        privacy_technique = data.get("privacy_technique", "none")
        privacy_parameter = data.get("privacy_parameter")
        self._validate_parameter_consistency(privacy_technique, privacy_parameter)

        row = SyntheticDataset(
            organization_id=organization_id,
            created_by=actor_user_id,
            name=data["name"],
            generation_method=data["generation_method"],
            source_dataset_id=data.get("source_dataset_id"),
            privacy_technique=privacy_technique,
            privacy_parameter=privacy_parameter,
            validation_status=data.get("validation_status", "unvalidated"),
            validation_notes=data.get("validation_notes"),
            governance_gap_flag=False,
        )
        self._recompute_gap_flag(row, organization_id)
        self.db.add(row)
        self.db.flush()

        metadata_json = {"source": "api"}
        if row.governance_gap_flag:
            metadata_json = {
                "source": "api",
                "governance_gap": True,
                "severity": "high",
                "reason": self.gap_reason(row),
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

        effective_technique = changes.get("privacy_technique", row.privacy_technique)
        effective_parameter = changes.get("privacy_parameter", row.privacy_parameter)
        self._validate_parameter_consistency(effective_technique, effective_parameter)

        for field, value in changes.items():
            setattr(row, field, value)

        gap_changed = self._recompute_gap_flag(row, organization_id)
        self.db.flush()

        metadata_json = {"source": "api"}
        if row.governance_gap_flag and gap_changed:
            metadata_json = {
                "source": "api",
                "governance_gap": True,
                "severity": "high",
                "reason": self.gap_reason(row),
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

        gap_changed = self._recompute_gap_flag(row, organization_id)
        self.db.flush()

        metadata_json: dict[str, Any] = {"source": "api", "action": "validate"}
        if row.governance_gap_flag:
            metadata_json.update(
                {
                    "governance_gap": True,
                    "severity": "high",
                    "flag": "logical_contradiction" if row.privacy_technique == "none" else "weak_privacy_parameter",
                    "reason": self.gap_reason(row),
                    "gap_newly_flagged": gap_changed,
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
