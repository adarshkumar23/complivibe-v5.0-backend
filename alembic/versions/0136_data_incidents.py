"""data incidents

Revision ID: 0136_data_incidents
Revises: 0135_data_access_and_retention
Create Date: 2026-06-26 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0136_data_incidents"
down_revision: str | None = "0135_data_access_and_retention"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "data_incidents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("data_asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("detector_type", sa.String(length=50), nullable=False),
        sa.Column("detector_ref_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'new'")),
        sa.Column("rule_type", sa.String(length=50), nullable=True),
        sa.Column("evidence_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("linked_issue_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("detected_by", sa.String(length=20), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("resolved_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "detector_type IN ('anomaly_rule', 'quality_breach', 'retention_violation', 'residency_violation', 'manual')",
            name="ck_data_incidents_detector_type",
        ),
        sa.CheckConstraint("severity IN ('critical', 'high', 'medium', 'low')", name="ck_data_incidents_severity"),
        sa.CheckConstraint("status IN ('new', 'investigating', 'contained', 'resolved', 'dismissed')", name="ck_data_incidents_status"),
        sa.CheckConstraint("detected_by IN ('scheduler', 'rule_engine', 'manual', 'api')", name="ck_data_incidents_detected_by"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["data_asset_id"], ["data_assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resolved_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_data_incidents_org_asset_status", "data_incidents", ["organization_id", "data_asset_id", "status"], unique=False)
    op.create_index("ix_data_incidents_org_severity_status", "data_incidents", ["organization_id", "severity", "status"], unique=False)
    op.create_index("ix_data_incidents_org_detector", "data_incidents", ["organization_id", "detector_type"], unique=False)
    op.create_index("ix_data_incidents_detected_at", "data_incidents", ["detected_at"], unique=False)

    # Extend issues source_type to allow data incident polymorphic links.
    op.drop_constraint("ck_issues_source_type", "issues", type_="check")
    op.create_check_constraint(
        "ck_issues_source_type",
        "issues",
        "source_type IN ('manual', 'monitoring_alert', 'audit_finding', 'vendor_assessment', 'external_report', 'data_incident')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_issues_source_type", "issues", type_="check")
    op.create_check_constraint(
        "ck_issues_source_type",
        "issues",
        "source_type IN ('manual', 'monitoring_alert', 'audit_finding', 'vendor_assessment', 'external_report')",
    )

    op.drop_index("ix_data_incidents_detected_at", table_name="data_incidents")
    op.drop_index("ix_data_incidents_org_detector", table_name="data_incidents")
    op.drop_index("ix_data_incidents_org_severity_status", table_name="data_incidents")
    op.drop_index("ix_data_incidents_org_asset_status", table_name="data_incidents")
    op.drop_table("data_incidents")
