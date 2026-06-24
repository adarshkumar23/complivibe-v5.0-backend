"""continuous control monitoring foundation

Revision ID: 0088_continuous_control_monitoring_foundation
Revises: 0087_vendor_risk_scoring_and_control_linkage
Create Date: 2026-06-23 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0088_continuous_control_monitoring_foundation"
down_revision: str | None = "0087_vendor_risk_scoring_and_control_linkage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "control_monitoring_definitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("control_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("monitoring_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("check_frequency", sa.String(length=32), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_check_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tags_json", sa.JSON(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("archive_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["control_id"], ["controls.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["archived_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_control_monitoring_definitions_organization_id",
        "control_monitoring_definitions",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_control_monitoring_definitions_org_status",
        "control_monitoring_definitions",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_control_monitoring_definitions_org_type",
        "control_monitoring_definitions",
        ["organization_id", "monitoring_type"],
        unique=False,
    )
    op.create_index(
        "ix_control_monitoring_definitions_org_control",
        "control_monitoring_definitions",
        ["organization_id", "control_id"],
        unique=False,
    )
    op.create_index(
        "ix_control_monitoring_definitions_org_owner",
        "control_monitoring_definitions",
        ["organization_id", "owner_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_control_monitoring_definitions_org_next_due",
        "control_monitoring_definitions",
        ["organization_id", "next_check_due_at"],
        unique=False,
    )

    op.create_table(
        "control_monitoring_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("definition_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("control_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("check_status", sa.String(length=32), nullable=False),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("result_detail_json", sa.JSON(), nullable=True),
        sa.Column("checked_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_check_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["definition_id"], ["control_monitoring_definitions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["control_id"], ["controls.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["checked_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_control_monitoring_results_organization_id",
        "control_monitoring_results",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_control_monitoring_results_org_definition",
        "control_monitoring_results",
        ["organization_id", "definition_id"],
        unique=False,
    )
    op.create_index(
        "ix_control_monitoring_results_org_control",
        "control_monitoring_results",
        ["organization_id", "control_id"],
        unique=False,
    )
    op.create_index(
        "ix_control_monitoring_results_org_status",
        "control_monitoring_results",
        ["organization_id", "check_status"],
        unique=False,
    )
    op.create_index(
        "ix_control_monitoring_results_org_checked",
        "control_monitoring_results",
        ["organization_id", "checked_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_control_monitoring_results_org_checked", table_name="control_monitoring_results")
    op.drop_index("ix_control_monitoring_results_org_status", table_name="control_monitoring_results")
    op.drop_index("ix_control_monitoring_results_org_control", table_name="control_monitoring_results")
    op.drop_index("ix_control_monitoring_results_org_definition", table_name="control_monitoring_results")
    op.drop_index("ix_control_monitoring_results_organization_id", table_name="control_monitoring_results")
    op.drop_table("control_monitoring_results")

    op.drop_index("ix_control_monitoring_definitions_org_next_due", table_name="control_monitoring_definitions")
    op.drop_index("ix_control_monitoring_definitions_org_owner", table_name="control_monitoring_definitions")
    op.drop_index("ix_control_monitoring_definitions_org_control", table_name="control_monitoring_definitions")
    op.drop_index("ix_control_monitoring_definitions_org_type", table_name="control_monitoring_definitions")
    op.drop_index("ix_control_monitoring_definitions_org_status", table_name="control_monitoring_definitions")
    op.drop_index("ix_control_monitoring_definitions_organization_id", table_name="control_monitoring_definitions")
    op.drop_table("control_monitoring_definitions")
