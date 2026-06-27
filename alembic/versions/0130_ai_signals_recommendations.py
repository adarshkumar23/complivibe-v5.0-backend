"""ai risk signals and recommendations

Revision ID: 0130_ai_signals_recommendations
Revises: 0129_ai_monitoring_mode_b
Create Date: 2026-06-25 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0130_ai_signals_recommendations"
down_revision: str | None = "0129_ai_monitoring_mode_b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_risk_signals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ai_system_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("signal_type", sa.String(length=50), nullable=False),
        sa.Column("signal_description", sa.Text(), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'new'")),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "signal_type IN ('new_training_data_source', 'deployment_scope_expansion', 'model_version_change', 'output_distribution_shift', 'new_use_case', 'new_geographic_deployment', 'high_volume_threshold_exceeded', 'bias_signal')",
            name="ck_ai_risk_signals_signal_type",
        ),
        sa.CheckConstraint(
            "severity IN ('critical', 'high', 'medium', 'low')",
            name="ck_ai_risk_signals_severity",
        ),
        sa.CheckConstraint(
            "status IN ('new', 'reviewed', 'actioned', 'dismissed')",
            name="ck_ai_risk_signals_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_risk_signals_org_system_status",
        "ai_risk_signals",
        ["organization_id", "ai_system_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_ai_risk_signals_org_type",
        "ai_risk_signals",
        ["organization_id", "signal_type"],
        unique=False,
    )
    op.create_index("ix_ai_risk_signals_detected_at", "ai_risk_signals", ["detected_at"], unique=False)

    op.create_table(
        "ai_risk_recommendations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ai_system_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_type", sa.String(length=30), nullable=False),
        sa.Column("recommendation_text", sa.Text(), nullable=False),
        sa.Column("recommendation_category", sa.String(length=30), nullable=False),
        sa.Column("priority", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'active'")),
        sa.Column("source_ref_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "source_type IN ('risk_assessment', 'monitoring_breach', 'signal', 'manual')",
            name="ck_ai_risk_recommendations_source_type",
        ),
        sa.CheckConstraint(
            "recommendation_category IN ('technical_control', 'process_control', 'documentation', 'audit', 'decommission')",
            name="ck_ai_risk_recommendations_category",
        ),
        sa.CheckConstraint(
            "priority IN ('critical', 'high', 'medium', 'low')",
            name="ck_ai_risk_recommendations_priority",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'applied', 'dismissed')",
            name="ck_ai_risk_recommendations_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_risk_recommendations_org_system_status",
        "ai_risk_recommendations",
        ["organization_id", "ai_system_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_ai_risk_recommendations_org_source_type",
        "ai_risk_recommendations",
        ["organization_id", "source_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ai_risk_recommendations_org_source_type", table_name="ai_risk_recommendations")
    op.drop_index("ix_ai_risk_recommendations_org_system_status", table_name="ai_risk_recommendations")
    op.drop_table("ai_risk_recommendations")

    op.drop_index("ix_ai_risk_signals_detected_at", table_name="ai_risk_signals")
    op.drop_index("ix_ai_risk_signals_org_type", table_name="ai_risk_signals")
    op.drop_index("ix_ai_risk_signals_org_system_status", table_name="ai_risk_signals")
    op.drop_table("ai_risk_signals")
