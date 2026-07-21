import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin

# Vocabularies for this table. Kept here, beside the constraints they police, so the
# model and the CHECK can never drift. Migrations 0320/0323 deliberately restate them
# rather than importing: a migration must keep describing the schema as it was when it
# ran, even after these lists change.

#: Core's original six (Feature #66). Never remove one -- live configs use them.
CORE_METRIC_TYPES = (
    "accuracy",
    "bias_parity_gap",
    "output_drift",
    "confidence_distribution",
    "response_time",
    "error_rate",
)

#: Patent P4's vocabulary. `drift`/`output_drift` and `bias`/`bias_parity_gap` are
#: near-synonyms kept separate on purpose: core's are user-chosen labels, P4's name a
#: specific computation. Merging them would silently change what an existing threshold
#: means.
P4_METRIC_TYPES = (
    "drift",
    "data_quality",
    "bias",
    "estimated_accuracy",
    "hallucination_rate",
    "rag_faithfulness",
    "rag_answer_relevancy",
    "token_cost",
    "latency_p95",
    "refusal_rate",
    "drift_seasonal",
    "bias_seasonal",
    "estimated_accuracy_seasonal",
    "prompt_injection_rate",
    "rag_context_precision",
    "rag_context_recall",
)
ALL_METRIC_TYPES = CORE_METRIC_TYPES + P4_METRIC_TYPES

THRESHOLD_OPERATORS = ("gt", "lt", "gte", "lte")

#: Everything the DB permits in workflow_to_trigger.
WORKFLOW_VALUES = (
    "create_alert",
    "create_issue",
    "update_risk_score",
    "require_review",
    "suspend_system",
    "notify_oncall",
)

#: DEFINED BUT NOT SELECTABLE.
#:
#: `suspend_system` has no implementation anywhere in core and no agreed meaning --
#: whether "suspended" is a label, a governance block, or a real halt of production
#: traffic is an open product decision that was never taken. It is the
#: highest-consequence workflow in the list, so an unimplemented one must not be
#: offerable: a customer selecting it would believe their AI system gets stopped on a
#: breach, and nothing whatsoever would happen.
#:
#: It stays in WORKFLOW_VALUES (the DB accepts it) so the column can hold the value if
#: it is ever implemented, and so an existing row is never invalidated. Every inbound
#: schema must validate against SELECTABLE_WORKFLOW_VALUES instead, and the dispatch
#: path must refuse it explicitly rather than silently no-op.
DISABLED_WORKFLOW_VALUES = ("suspend_system",)
SELECTABLE_WORKFLOW_VALUES = tuple(v for v in WORKFLOW_VALUES if v not in DISABLED_WORKFLOW_VALUES)


def _sql_in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


class AIMonitoringConfig(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "ai_monitoring_configs"
    __table_args__ = (
        CheckConstraint(
            f"metric_type IN ({_sql_in(ALL_METRIC_TYPES)})",
            name="ck_ai_monitoring_configs_metric_type",
        ),
        CheckConstraint(
            "comparison_direction IN ('above', 'below')",
            name="ck_ai_monitoring_configs_comparison_direction",
        ),
        CheckConstraint(
            "check_frequency IS NULL OR check_frequency IN ('realtime', 'hourly', 'daily', 'weekly')",
            name="ck_ai_monitoring_configs_check_frequency",
        ),
        CheckConstraint(
            f"threshold_operator IN ({_sql_in(THRESHOLD_OPERATORS)})",
            name="ck_ai_monitoring_configs_threshold_operator",
        ),
        CheckConstraint(
            f"workflow_to_trigger IN ({_sql_in(WORKFLOW_VALUES)})",
            name="ck_ai_monitoring_configs_workflow_to_trigger",
        ),
        Index("ix_ai_monitoring_configs_org_system_active", "organization_id", "ai_system_id", "is_active"),
        Index("ix_ai_monitoring_configs_org_metric", "organization_id", "metric_type"),
        Index("ix_ai_monitoring_configs_obligation", "obligation_id"),
        # One ACTIVE config per (system, metric, tier). Several tiers may be active on
        # one metric -- that is the point of tiers -- but a duplicate tier is ambiguous.
        # Partial on is_active so superseded configs are retained for audit.
        Index(
            "uq_ai_monitoring_configs_active_tier",
            "ai_system_id",
            "metric_type",
            "tier",
            unique=True,
            postgresql_where=text("is_active"),
            sqlite_where=text("is_active"),
        ),
    )

    ai_system_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("ai_systems.id", ondelete="CASCADE"), nullable=False)
    metric_type: Mapped[str] = mapped_column(String(50), nullable=False)
    threshold_value: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    comparison_direction: Mapped[str] = mapped_column(String(10), nullable=False)
    alert_on_breach: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    check_frequency: Mapped[str | None] = mapped_column(String(20), nullable=True)
    baseline_value: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    # Snapshot of AISystem.model_version at the time the baseline was recorded.
    # Used to flag a stale/pre-model-change baseline in the monitoring dashboard.
    baseline_model_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_reading_value: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    api_key_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- patent P4 compliance-decision layer (migration 0320) ---------------------
    # The regulatory duty the threshold derives from. NULLABLE on purpose: a threshold
    # may exist before compliance links it to an obligation, and asserting provenance
    # for a hand-picked number would be exactly the dishonesty this column exists to
    # prevent. FK is SET NULL, matching controls.obligation_id -- retiring an
    # obligation must neither delete a customer's threshold nor be blocked by it.
    obligation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("obligations.id", ondelete="SET NULL"), nullable=True
    )
    # Severity label. 'default' is what the 0320 backfill assigned to configs that
    # predate tiering -- deliberately not 'warning', since nobody chose a severity for
    # those and calling them 'warning' would assert one.
    tier: Mapped[str] = mapped_column(String(32), nullable=False, default="default")
    # Ordering and reporting only. Never used to skip a tier: every breached tier fires.
    escalation_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Strictly more expressive than comparison_direction, which is retained unchanged.
    # 'above' == 'gte' and 'below' == 'lte' exactly, per check_threshold.
    threshold_operator: Mapped[str] = mapped_column(String(8), nullable=False, default="gte")
    workflow_to_trigger: Mapped[str] = mapped_column(String(32), nullable=False, default="create_alert")
