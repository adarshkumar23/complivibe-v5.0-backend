import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin

RISK_DEPENDENCY_RELATIONSHIP_TYPES = ("cascades_to", "triggers", "compounds")


class RiskDependency(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    """A directed risk-to-risk relationship: upstream_risk_id materializing can affect
    (cascade into/trigger/compound) downstream_risk_id.

    This is a genuinely separate concept from RiskControlLink/RiskEvidenceLink (which
    connect a risk to its mitigating controls/evidence) and from RiskGraphService (which
    builds a risk<->control/vendor/evidence/obligation/policy coverage graph). This table
    is pure risk-to-risk, for cascade/dependency analysis.
    """

    __tablename__ = "risk_dependencies"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "upstream_risk_id",
            "downstream_risk_id",
            name="uq_risk_dependency_edge",
        ),
        CheckConstraint("upstream_risk_id != downstream_risk_id", name="ck_risk_dependency_no_self_loop"),
        CheckConstraint(
            "relationship_type IN ('cascades_to', 'triggers', 'compounds')",
            name="ck_risk_dependency_relationship_type",
        ),
        Index("ix_risk_dependencies_upstream_risk_id", "upstream_risk_id"),
        Index("ix_risk_dependencies_downstream_risk_id", "downstream_risk_id"),
    )

    upstream_risk_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("risks.id", ondelete="CASCADE"),
        nullable=False,
    )
    downstream_risk_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("risks.id", ondelete="CASCADE"),
        nullable=False,
    )
    relationship_type: Mapped[str] = mapped_column(String(32), nullable=False, default="cascades_to")
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
