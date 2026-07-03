"""ai risk classification review controls and governance signals foundation

Revision ID: 0069_ai_risk_classification_review_signals
Revises: 0068_ai_risk_classification_foundation
Create Date: 2026-06-20 21:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0069_ai_risk_classification_review_signals"
down_revision: str | None = "0068_ai_risk_classification_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ai_system_risk_classification_records",
        sa.Column("review_status", sa.String(length=32), nullable=False, server_default="not_submitted"),
    )
    op.add_column(
        "ai_system_risk_classification_records",
        sa.Column("review_requested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "ai_system_risk_classification_records",
        sa.Column("review_requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "ai_system_risk_classification_records",
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "ai_system_risk_classification_records",
        sa.Column("reviewed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "ai_system_risk_classification_records",
        sa.Column("review_note", sa.Text(), nullable=True),
    )
    op.add_column(
        "ai_system_risk_classification_records",
        sa.Column("change_request_note", sa.Text(), nullable=True),
    )
    op.add_column(
        "ai_system_risk_classification_records",
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "ai_system_risk_classification_records",
        sa.Column("rejected_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "ai_system_risk_classification_records",
        sa.Column("rejection_reason", sa.Text(), nullable=True),
    )

    op.create_foreign_key(
        "fk_ai_risk_classification_records_review_requested_by_user_id",
        "ai_system_risk_classification_records",
        "users",
        ["review_requested_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_ai_risk_classification_records_reviewed_by_user_id",
        "ai_system_risk_classification_records",
        "users",
        ["reviewed_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_ai_risk_classification_records_rejected_by_user_id",
        "ai_system_risk_classification_records",
        "users",
        ["rejected_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column(
        "ai_system_risk_assessments",
        sa.Column("latest_classification_review_status", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "ai_system_risk_assessments",
        sa.Column("open_signal_count", sa.Integer(), nullable=True),
    )

    op.create_table(
        "ai_system_risk_classification_record_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("classification_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("risk_assessment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ai_system_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_type", sa.String(length=64), nullable=False),
        sa.Column("snapshot_version", sa.Integer(), nullable=False),
        sa.Column("snapshot_json", sa.JSON(), nullable=False),
        sa.Column("snapshot_sha256", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["classification_id"],
            ["ai_system_risk_classification_records.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["risk_assessment_id"], ["ai_system_risk_assessments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_system_risk_class_record_snaps_org_id_c0feb594",
        "ai_system_risk_classification_record_snapshots",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_risk_classification_record_snapshots_org_classification",
        "ai_system_risk_classification_record_snapshots",
        ["organization_id", "classification_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_risk_classification_record_snapshots_org_assessment",
        "ai_system_risk_classification_record_snapshots",
        ["organization_id", "risk_assessment_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_risk_classification_record_snapshots_org_ai_system",
        "ai_system_risk_classification_record_snapshots",
        ["organization_id", "ai_system_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_risk_classification_record_snapshots_org_type",
        "ai_system_risk_classification_record_snapshots",
        ["organization_id", "snapshot_type"],
        unique=False,
    )
    op.create_index(
        "ix_ai_risk_class_record_snaps_org_class_ver_7933f4bd",
        "ai_system_risk_classification_record_snapshots",
        ["organization_id", "classification_id", "snapshot_version"],
        unique=False,
    )

    op.create_table(
        "governance_signals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("domain", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("related_ai_system_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("related_risk_assessment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("signal_type", sa.String(length=128), nullable=False),
        sa.Column("reason_code", sa.String(length=128), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("source_json", sa.JSON(), nullable=False),
        sa.Column("created_by_system", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolve_reason", sa.Text(), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("dismiss_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["related_ai_system_id"], ["ai_systems.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["related_risk_assessment_id"], ["ai_system_risk_assessments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["resolved_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["dismissed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_governance_signals_organization_id", "governance_signals", ["organization_id"], unique=False)
    op.create_index("ix_governance_signals_org_domain", "governance_signals", ["organization_id", "domain"], unique=False)
    op.create_index(
        "ix_governance_signals_org_entity",
        "governance_signals",
        ["organization_id", "entity_type", "entity_id"],
        unique=False,
    )
    op.create_index(
        "ix_governance_signals_org_ai_system",
        "governance_signals",
        ["organization_id", "related_ai_system_id"],
        unique=False,
    )
    op.create_index(
        "ix_governance_signals_org_assessment",
        "governance_signals",
        ["organization_id", "related_risk_assessment_id"],
        unique=False,
    )
    op.create_index(
        "ix_governance_signals_org_signal_type",
        "governance_signals",
        ["organization_id", "signal_type"],
        unique=False,
    )
    op.create_index(
        "ix_governance_signals_org_reason_code",
        "governance_signals",
        ["organization_id", "reason_code"],
        unique=False,
    )
    op.create_index(
        "ix_governance_signals_org_severity",
        "governance_signals",
        ["organization_id", "severity"],
        unique=False,
    )
    op.create_index(
        "ix_governance_signals_org_status",
        "governance_signals",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_governance_signals_org_created",
        "governance_signals",
        ["organization_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_governance_signals_org_created", table_name="governance_signals")
    op.drop_index("ix_governance_signals_org_status", table_name="governance_signals")
    op.drop_index("ix_governance_signals_org_severity", table_name="governance_signals")
    op.drop_index("ix_governance_signals_org_reason_code", table_name="governance_signals")
    op.drop_index("ix_governance_signals_org_signal_type", table_name="governance_signals")
    op.drop_index("ix_governance_signals_org_assessment", table_name="governance_signals")
    op.drop_index("ix_governance_signals_org_ai_system", table_name="governance_signals")
    op.drop_index("ix_governance_signals_org_entity", table_name="governance_signals")
    op.drop_index("ix_governance_signals_org_domain", table_name="governance_signals")
    op.drop_index("ix_governance_signals_organization_id", table_name="governance_signals")
    op.drop_table("governance_signals")

    op.drop_index(
        "ix_ai_risk_class_record_snaps_org_class_ver_7933f4bd",
        table_name="ai_system_risk_classification_record_snapshots",
    )
    op.drop_index("ix_ai_risk_classification_record_snapshots_org_type", table_name="ai_system_risk_classification_record_snapshots")
    op.drop_index(
        "ix_ai_risk_classification_record_snapshots_org_ai_system",
        table_name="ai_system_risk_classification_record_snapshots",
    )
    op.drop_index(
        "ix_ai_risk_classification_record_snapshots_org_assessment",
        table_name="ai_system_risk_classification_record_snapshots",
    )
    op.drop_index(
        "ix_ai_risk_classification_record_snapshots_org_classification",
        table_name="ai_system_risk_classification_record_snapshots",
    )
    op.drop_index(
        "ix_ai_system_risk_class_record_snaps_org_id_c0feb594",
        table_name="ai_system_risk_classification_record_snapshots",
    )
    op.drop_table("ai_system_risk_classification_record_snapshots")

    op.drop_column("ai_system_risk_assessments", "open_signal_count")
    op.drop_column("ai_system_risk_assessments", "latest_classification_review_status")

    op.drop_constraint(
        "fk_ai_risk_classification_records_rejected_by_user_id",
        "ai_system_risk_classification_records",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_ai_risk_classification_records_reviewed_by_user_id",
        "ai_system_risk_classification_records",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_ai_risk_classification_records_review_requested_by_user_id",
        "ai_system_risk_classification_records",
        type_="foreignkey",
    )
    op.drop_column("ai_system_risk_classification_records", "rejection_reason")
    op.drop_column("ai_system_risk_classification_records", "rejected_by_user_id")
    op.drop_column("ai_system_risk_classification_records", "rejected_at")
    op.drop_column("ai_system_risk_classification_records", "change_request_note")
    op.drop_column("ai_system_risk_classification_records", "review_note")
    op.drop_column("ai_system_risk_classification_records", "reviewed_by_user_id")
    op.drop_column("ai_system_risk_classification_records", "reviewed_at")
    op.drop_column("ai_system_risk_classification_records", "review_requested_by_user_id")
    op.drop_column("ai_system_risk_classification_records", "review_requested_at")
    op.drop_column("ai_system_risk_classification_records", "review_status")
