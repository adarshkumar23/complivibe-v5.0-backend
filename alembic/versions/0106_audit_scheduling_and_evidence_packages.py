"""audit scheduling and evidence packages

Revision ID: 0106_audit_scheduling_and_evidence_packages
Revises: 0105_auditor_portal_and_audit_findings
Create Date: 2026-06-24 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0106_audit_scheduling_and_evidence_packages"
down_revision: str | None = "0105_auditor_portal_and_audit_findings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_schedules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("audit_type", sa.String(length=50), nullable=False),
        sa.Column("framework_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recurrence_pattern", sa.String(length=50), nullable=False),
        sa.Column("next_audit_date", sa.Date(), nullable=False),
        sa.Column("preparation_reminder_days", sa.Integer(), nullable=False, server_default=sa.text("30")),
        sa.Column("last_reminder_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_audit_engagement_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default=sa.text("'active'")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "audit_type IN ('internal_readiness', 'external_certification', 'surveillance', 'gap_assessment')",
            name="ck_audit_schedules_audit_type",
        ),
        sa.CheckConstraint(
            "recurrence_pattern IN ('annual', 'semi_annual', 'quarterly', 'monthly')",
            name="ck_audit_schedules_recurrence_pattern",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'paused', 'cancelled')",
            name="ck_audit_schedules_status",
        ),
        sa.CheckConstraint(
            "preparation_reminder_days BETWEEN 7 AND 90",
            name="ck_audit_schedules_preparation_reminder_days",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["framework_id"], ["frameworks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["last_audit_engagement_id"], ["audit_engagements.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_schedules_organization_id", "audit_schedules", ["organization_id"], unique=False)
    op.create_index("ix_audit_schedules_org_status", "audit_schedules", ["organization_id", "status"], unique=False)
    op.create_index("ix_audit_schedules_org_framework", "audit_schedules", ["organization_id", "framework_id"], unique=False)
    op.create_index("ix_audit_schedules_next_date_status", "audit_schedules", ["next_audit_date", "status"], unique=False)

    op.create_table(
        "evidence_packages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("audit_engagement_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("scope_framework_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("cover_sheet_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("chain_of_custody", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("status", sa.String(length=50), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("assembled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assembled_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("exported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("item_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('draft', 'assembled', 'exported', 'archived')",
            name="ck_evidence_packages_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["audit_engagement_id"], ["audit_engagements.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assembled_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evidence_packages_organization_id", "evidence_packages", ["organization_id"], unique=False)
    op.create_index(
        "ix_evidence_packages_org_engagement",
        "evidence_packages",
        ["organization_id", "audit_engagement_id"],
        unique=False,
    )
    op.create_index("ix_evidence_packages_org_status", "evidence_packages", ["organization_id", "status"], unique=False)

    op.create_table(
        "evidence_package_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("package_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("control_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("framework_requirement_ref", sa.String(length=255), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("added_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["package_id"], ["evidence_packages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["control_id"], ["controls.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence_items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["added_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("package_id", "evidence_id", name="uq_evidence_package_items_package_evidence"),
    )
    op.create_index("ix_evidence_package_items_package_id", "evidence_package_items", ["package_id"], unique=False)
    op.create_index(
        "ix_evidence_package_items_package_framework_ref",
        "evidence_package_items",
        ["package_id", "framework_requirement_ref"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_evidence_package_items_package_framework_ref", table_name="evidence_package_items")
    op.drop_index("ix_evidence_package_items_package_id", table_name="evidence_package_items")
    op.drop_table("evidence_package_items")

    op.drop_index("ix_evidence_packages_org_status", table_name="evidence_packages")
    op.drop_index("ix_evidence_packages_org_engagement", table_name="evidence_packages")
    op.drop_index("ix_evidence_packages_organization_id", table_name="evidence_packages")
    op.drop_table("evidence_packages")

    op.drop_index("ix_audit_schedules_next_date_status", table_name="audit_schedules")
    op.drop_index("ix_audit_schedules_org_framework", table_name="audit_schedules")
    op.drop_index("ix_audit_schedules_org_status", table_name="audit_schedules")
    op.drop_index("ix_audit_schedules_organization_id", table_name="audit_schedules")
    op.drop_table("audit_schedules")
