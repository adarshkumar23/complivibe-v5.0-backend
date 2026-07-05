import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin

# The T4-13 TrainingDataset model (table `training_datasets`) may not be
# imported into Base.metadata yet depending on import order in
# app/models/__init__.py. SQLAlchemy's metadata.create_all() eagerly resolves
# every ForeignKey target to sort DDL, so declaring a FK to a table that is
# not (yet) present in Base.metadata breaks table creation for the *entire*
# test/dev database, not just this model. Only attach the real FK constraint
# once `training_datasets` is present in metadata; otherwise fall back to a
# plain (unconstrained) UUID column. Once app/models/__init__.py imports
# training_dataset before synthetic_dataset, this activates automatically --
# no further change needed here.
_SOURCE_DATASET_FK_ARGS = (
    (ForeignKey("training_datasets.id", ondelete="SET NULL"),)
    if "training_datasets" in Base.metadata.tables
    else ()
)


class SyntheticDataset(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "synthetic_datasets"
    __table_args__ = (
        CheckConstraint(
            "privacy_technique IN ('differential_privacy', 'k_anonymity', 'none')",
            name="ck_synthetic_datasets_privacy_technique",
        ),
        CheckConstraint(
            "validation_status IN ('unvalidated', 'validated', 'failed_validation')",
            name="ck_synthetic_datasets_validation_status",
        ),
        Index("ix_synthetic_datasets_org_validation_status", "organization_id", "validation_status"),
        Index("ix_synthetic_datasets_org_privacy_technique", "organization_id", "privacy_technique"),
        Index("ix_synthetic_datasets_org_gap_flag", "organization_id", "governance_gap_flag"),
        CheckConstraint(
            "reidentification_risk_score IS NULL OR "
            "(reidentification_risk_score >= 0.0 AND reidentification_risk_score <= 1.0)",
            name="ck_synthetic_datasets_risk_score_range",
        ),
        CheckConstraint(
            "privacy_parameter IS NULL OR privacy_parameter > 0.0",
            name="ck_synthetic_datasets_privacy_parameter_positive",
        ),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    generation_method: Mapped[str] = mapped_column(String(255), nullable=False)
    source_dataset_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, *_SOURCE_DATASET_FK_ARGS, nullable=True
    )
    privacy_technique: Mapped[str] = mapped_column(String(50), nullable=False, default="none")
    # Quantified privacy parameter behind privacy_technique: k (equivalence-class
    # size) for k_anonymity, or epsilon for differential_privacy. None for 'none'.
    privacy_parameter: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Estimated worst-case re-identification / membership-inference probability
    # (0.0-1.0), computed from privacy_technique + privacy_parameter using
    # established bounds (1/k for k-anonymity; e^eps/(1+e^eps) for eps-DP
    # membership inference). Recomputed on every write; never hand-entered.
    reidentification_risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    validation_status: Mapped[str] = mapped_column(String(50), nullable=False, default="unvalidated")
    validation_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    governance_gap_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
