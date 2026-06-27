"""auditor portal invitations and audit findings

Revision ID: 0105_auditor_portal_and_audit_findings
Revises: 0104_audit_planning_and_pbc_items
Create Date: 2026-06-24 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0105_auditor_portal_and_audit_findings"
down_revision: str | None = "0104_audit_planning_and_pbc_items"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "auditor_portal_invitations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("audit_engagement_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("auditor_email", sa.String(length=255), nullable=False),
        sa.Column("auditor_name", sa.String(length=255), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("scoped_framework_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("scoped_control_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("scoped_evidence_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("first_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("access_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("status", sa.String(length=50), nullable=False, server_default=sa.text("'active'")),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "status IN ('active', 'revoked', 'expired')",
            name="ck_auditor_portal_invitations_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["audit_engagement_id"], ["audit_engagements.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["revoked_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_auditor_portal_invitations_token_hash",
        "auditor_portal_invitations",
        ["token_hash"],
        unique=False,
    )
    op.create_index(
        "ix_auditor_portal_invitations_org_engagement",
        "auditor_portal_invitations",
        ["organization_id", "audit_engagement_id"],
        unique=False,
    )
    op.create_index(
        "ix_auditor_portal_invitations_org_status",
        "auditor_portal_invitations",
        ["organization_id", "status"],
        unique=False,
    )

    op.create_table(
        "audit_findings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("audit_engagement_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("finding_ref", sa.String(length=50), nullable=False),
        sa.Column("severity", sa.String(length=50), nullable=False),
        sa.Column("framework_ref", sa.String(length=255), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("assigned_owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("remediation_action", sa.Text(), nullable=False),
        sa.Column("target_remediation_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default=sa.text("'open'")),
        sa.Column("risk_register_entry_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("control_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "severity IN ('critical', 'high', 'medium', 'low', 'informational')",
            name="ck_audit_findings_severity",
        ),
        sa.CheckConstraint(
            "status IN ('open', 'in_remediation', 'remediated', 'closed', 'risk_accepted')",
            name="ck_audit_findings_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["audit_engagement_id"], ["audit_engagements.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assigned_owner_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["risk_register_entry_id"], ["risks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["control_id"], ["controls.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["closed_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "finding_ref", name="uq_audit_findings_org_ref"),
    )
    op.create_index("ix_audit_findings_organization_id", "audit_findings", ["organization_id"], unique=False)
    op.create_index(
        "ix_audit_findings_org_engagement",
        "audit_findings",
        ["organization_id", "audit_engagement_id"],
        unique=False,
    )
    op.create_index(
        "ix_audit_findings_org_status_severity",
        "audit_findings",
        ["organization_id", "status", "severity"],
        unique=False,
    )
    op.create_index(
        "ix_audit_findings_org_assigned_owner",
        "audit_findings",
        ["organization_id", "assigned_owner_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_audit_findings_org_assigned_owner", table_name="audit_findings")
    op.drop_index("ix_audit_findings_org_status_severity", table_name="audit_findings")
    op.drop_index("ix_audit_findings_org_engagement", table_name="audit_findings")
    op.drop_index("ix_audit_findings_organization_id", table_name="audit_findings")
    op.drop_table("audit_findings")

    op.drop_index("ix_auditor_portal_invitations_org_status", table_name="auditor_portal_invitations")
    op.drop_index("ix_auditor_portal_invitations_org_engagement", table_name="auditor_portal_invitations")
    op.drop_index("ix_auditor_portal_invitations_token_hash", table_name="auditor_portal_invitations")
    op.drop_table("auditor_portal_invitations")
