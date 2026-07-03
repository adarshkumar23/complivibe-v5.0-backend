"""pbc requests and audit findings refresh

Revision ID: 0188_pbc_requests_audit_findings_refresh
Revises: 0187_issue_policy_linking_refresh
Create Date: 2026-07-01 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0188_pbc_requests_audit_findings_refresh"
down_revision: str | None = "0187_issue_policy_linking_refresh"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pbc_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("audit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("item_description", sa.Text(), nullable=False),
        sa.Column("assigned_to", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'open'")),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "status IN ('open', 'submitted', 'accepted', 'rejected', 'overdue')",
            name="ck_pbc_requests_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["audit_id"], ["audit_engagements.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assigned_to"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence_items.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pbc_requests_org_audit", "pbc_requests", ["organization_id", "audit_id"], unique=False)
    op.create_index("ix_pbc_requests_org_status", "pbc_requests", ["organization_id", "status"], unique=False)
    op.create_index("ix_pbc_requests_org_due", "pbc_requests", ["organization_id", "due_date"], unique=False)
    op.create_index("ix_pbc_requests_assigned_to", "pbc_requests", ["assigned_to"], unique=False)

    op.add_column("audit_findings", sa.Column("audit_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("audit_findings", sa.Column("finding_type", sa.String(length=50), nullable=False, server_default=sa.text("'observation'")))
    op.add_column("audit_findings", sa.Column("remediation_plan", sa.Text(), nullable=True))
    op.add_column("audit_findings", sa.Column("remediation_due_date", sa.Date(), nullable=True))
    op.add_column("audit_findings", sa.Column("remediation_owner_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("audit_findings", sa.Column("linked_risk_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("audit_findings", sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("audit_findings", sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True))

    op.execute("UPDATE audit_findings SET audit_id = audit_engagement_id WHERE audit_id IS NULL")
    op.execute("UPDATE audit_findings SET remediation_plan = remediation_action WHERE remediation_plan IS NULL")
    op.execute("UPDATE audit_findings SET remediation_due_date = target_remediation_date WHERE remediation_due_date IS NULL")
    op.execute("UPDATE audit_findings SET remediation_owner_id = assigned_owner_id WHERE remediation_owner_id IS NULL")
    op.execute("UPDATE audit_findings SET linked_risk_id = risk_register_entry_id WHERE linked_risk_id IS NULL")
    op.execute("UPDATE audit_findings SET created_by = assigned_owner_id WHERE created_by IS NULL")
    op.execute("UPDATE audit_findings SET resolved_at = closed_at WHERE resolved_at IS NULL AND status IN ('resolved', 'remediated')")

    op.create_foreign_key("fk_audit_findings_audit_id", "audit_findings", "audit_engagements", ["audit_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_audit_findings_rem_owner", "audit_findings", "users", ["remediation_owner_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_audit_findings_linked_risk", "audit_findings", "risks", ["linked_risk_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_audit_findings_created_by", "audit_findings", "users", ["created_by"], ["id"], ondelete="RESTRICT")

    op.drop_constraint("ck_audit_findings_status", "audit_findings", type_="check")
    op.create_check_constraint(
        "ck_audit_findings_status_v2",
        "audit_findings",
        "status IN ('open', 'in_remediation', 'remediated', 'closed', 'risk_accepted', 'remediation_in_progress', 'resolved', 'accepted_risk')",
    )
    op.create_check_constraint(
        "ck_audit_findings_finding_type",
        "audit_findings",
        "finding_type IN ('observation', 'minor_nonconformity', 'major_nonconformity', 'opportunity_for_improvement')",
    )

    op.create_index("ix_audit_findings_org_audit_id", "audit_findings", ["organization_id", "audit_id"], unique=False)
    op.create_index("ix_audit_findings_org_status", "audit_findings", ["organization_id", "status"], unique=False)
    op.create_index("ix_audit_findings_org_severity", "audit_findings", ["organization_id", "severity"], unique=False)
    op.create_index("ix_audit_findings_control_id", "audit_findings", ["control_id"], unique=False)

    op.alter_column("audit_findings", "audit_id", nullable=False)
    op.alter_column("audit_findings", "created_by", nullable=False)


def downgrade() -> None:
    op.drop_index("ix_audit_findings_control_id", table_name="audit_findings")
    op.drop_index("ix_audit_findings_org_severity", table_name="audit_findings")
    op.drop_index("ix_audit_findings_org_status", table_name="audit_findings")
    op.drop_index("ix_audit_findings_org_audit_id", table_name="audit_findings")

    op.drop_constraint("ck_audit_findings_finding_type", "audit_findings", type_="check")
    op.drop_constraint("ck_audit_findings_status_v2", "audit_findings", type_="check")
    op.create_check_constraint(
        "ck_audit_findings_status",
        "audit_findings",
        "status IN ('open', 'in_remediation', 'remediated', 'closed', 'risk_accepted')",
    )

    op.drop_constraint("fk_audit_findings_created_by", "audit_findings", type_="foreignkey")
    op.drop_constraint("fk_audit_findings_linked_risk", "audit_findings", type_="foreignkey")
    op.drop_constraint("fk_audit_findings_rem_owner", "audit_findings", type_="foreignkey")
    op.drop_constraint("fk_audit_findings_audit_id", "audit_findings", type_="foreignkey")

    op.drop_column("audit_findings", "created_by")
    op.drop_column("audit_findings", "resolved_at")
    op.drop_column("audit_findings", "linked_risk_id")
    op.drop_column("audit_findings", "remediation_owner_id")
    op.drop_column("audit_findings", "remediation_due_date")
    op.drop_column("audit_findings", "remediation_plan")
    op.drop_column("audit_findings", "finding_type")
    op.drop_column("audit_findings", "audit_id")

    op.drop_index("ix_pbc_requests_assigned_to", table_name="pbc_requests")
    op.drop_index("ix_pbc_requests_org_due", table_name="pbc_requests")
    op.drop_index("ix_pbc_requests_org_status", table_name="pbc_requests")
    op.drop_index("ix_pbc_requests_org_audit", table_name="pbc_requests")
    op.drop_table("pbc_requests")
