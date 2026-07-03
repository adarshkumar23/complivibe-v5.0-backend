"""key risk indicators foundation

Revision ID: 0092_key_risk_indicators
Revises: 0091_compliance_calendar_deadline_management
Create Date: 2026-06-23 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0092_key_risk_indicators"
down_revision: str | None = "0091_compliance_calendar_deadline_management"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


metric_type_enum = postgresql.ENUM(
    "control_expiry_rate",
    "evidence_gap_rate",
    "overdue_task_rate",
    "vendor_high_risk_count",
    "open_alert_count",
    "policy_overdue_review",
    "custom",
    name="risk_indicator_metric_type_enum",
    create_type=False,
)

status_enum = postgresql.ENUM(
    "green",
    "amber",
    "red",
    "not_calculated",
    name="risk_indicator_status_enum",
    create_type=False,
)


def upgrade() -> None:
    metric_type_enum.create(op.get_bind(), checkfirst=True)
    status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "risk_indicators",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("metric_type", metric_type_enum, nullable=False),
        sa.Column("target_value", sa.Numeric(10, 4), nullable=False),
        sa.Column("warning_threshold", sa.Numeric(10, 4), nullable=False),
        sa.Column("critical_threshold", sa.Numeric(10, 4), nullable=False),
        sa.Column("current_value", sa.Numeric(10, 4), nullable=True),
        sa.Column("status", status_enum, server_default=sa.text("'not_calculated'"), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("linked_risk_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("last_calculated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("tags_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("archive_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["linked_risk_id"], ["risks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["archived_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_risk_indicators_organization_id", "risk_indicators", ["organization_id"], unique=False)
    op.create_index("ix_risk_indicators_org_active", "risk_indicators", ["organization_id", "is_active"], unique=False)
    op.create_index("ix_risk_indicators_org_metric_type", "risk_indicators", ["organization_id", "metric_type"], unique=False)
    op.create_index("ix_risk_indicators_org_status", "risk_indicators", ["organization_id", "status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_risk_indicators_org_status", table_name="risk_indicators")
    op.drop_index("ix_risk_indicators_org_metric_type", table_name="risk_indicators")
    op.drop_index("ix_risk_indicators_org_active", table_name="risk_indicators")
    op.drop_index("ix_risk_indicators_organization_id", table_name="risk_indicators")
    op.drop_table("risk_indicators")

    status_enum.drop(op.get_bind(), checkfirst=True)
    metric_type_enum.drop(op.get_bind(), checkfirst=True)
