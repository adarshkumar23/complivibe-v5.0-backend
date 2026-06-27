"""formal issue log

Revision ID: 0111_formal_issue_log
Revises: 0110_trust_center_ai_vendor_mitigation
Create Date: 2026-06-25 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0111_formal_issue_log"
down_revision: str | None = "0110_trust_center_ai_vendor_mitigation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "issues",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("issue_type", sa.String(length=50), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default=sa.text("'open'")),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assigned_to", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "issue_type IN ('security_incident', 'compliance_violation', 'operational_failure', 'vendor_failure', 'data_loss', 'unauthorized_access', 'policy_violation', 'custom')",
            name="ck_issues_issue_type",
        ),
        sa.CheckConstraint(
            "severity IN ('critical', 'high', 'medium', 'low')",
            name="ck_issues_severity",
        ),
        sa.CheckConstraint(
            "source_type IN ('manual', 'monitoring_alert', 'audit_finding', 'vendor_assessment', 'external_report')",
            name="ck_issues_source_type",
        ),
        sa.CheckConstraint(
            "status IN ('open', 'investigating', 'mitigating', 'resolved', 'closed')",
            name="ck_issues_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["assigned_to"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_issues_org_status", "issues", ["organization_id", "status"], unique=False)
    op.create_index("ix_issues_org_severity", "issues", ["organization_id", "severity"], unique=False)
    op.create_index("ix_issues_org_issue_type", "issues", ["organization_id", "issue_type"], unique=False)
    op.create_index("ix_issues_org_source", "issues", ["organization_id", "source_type", "source_id"], unique=False)
    op.create_index("ix_issues_org_owner", "issues", ["organization_id", "owner_id"], unique=False)
    op.create_index("ix_issues_created_at", "issues", ["created_at"], unique=False)

    op.create_table(
        "issue_transitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("issue_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("from_status", sa.String(length=50), nullable=False),
        sa.Column("to_status", sa.String(length=50), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("transitioned_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["issue_id"], ["issues.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_issue_transitions_issue_id", "issue_transitions", ["issue_id"], unique=False)
    op.create_index(
        "ix_issue_transitions_org_issue",
        "issue_transitions",
        ["organization_id", "issue_id"],
        unique=False,
    )

    op.create_table(
        "org_issue_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("require_rca_before_close", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", name="uq_org_issue_settings_organization_id"),
    )


def downgrade() -> None:
    op.drop_table("org_issue_settings")

    op.drop_index("ix_issue_transitions_org_issue", table_name="issue_transitions")
    op.drop_index("ix_issue_transitions_issue_id", table_name="issue_transitions")
    op.drop_table("issue_transitions")

    op.drop_index("ix_issues_created_at", table_name="issues")
    op.drop_index("ix_issues_org_owner", table_name="issues")
    op.drop_index("ix_issues_org_source", table_name="issues")
    op.drop_index("ix_issues_org_issue_type", table_name="issues")
    op.drop_index("ix_issues_org_severity", table_name="issues")
    op.drop_index("ix_issues_org_status", table_name="issues")
    op.drop_table("issues")
