"""policy exception management

Revision ID: 0100_policy_exception_management
Revises: 0099_employee_attestations
Create Date: 2026-06-24 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0100_policy_exception_management"
down_revision: str | None = "0099_employee_attestations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "policy_exceptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_version", sa.String(length=50), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.Column("compensating_measure", sa.Text(), nullable=True),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requestor_scope", sa.String(length=255), nullable=True),
        sa.Column("requested_expiry_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("approved_expiry_date", sa.Date(), nullable=True),
        sa.Column("risk_level", sa.String(length=20), server_default=sa.text("'medium'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'expired', 'withdrawn')",
            name="ck_policy_exceptions_status",
        ),
        sa.CheckConstraint(
            "risk_level IN ('low', 'medium', 'high', 'critical')",
            name="ck_policy_exceptions_risk_level",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["policy_id"], ["compliance_policies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_policy_exceptions_organization_id",
        "policy_exceptions",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_policy_exceptions_org_policy",
        "policy_exceptions",
        ["organization_id", "policy_id"],
        unique=False,
    )
    op.create_index(
        "ix_policy_exceptions_org_status",
        "policy_exceptions",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_policy_exceptions_org_requested_by",
        "policy_exceptions",
        ["organization_id", "requested_by"],
        unique=False,
    )
    op.create_index(
        "ix_policy_exceptions_org_status_approved_expiry",
        "policy_exceptions",
        ["organization_id", "status", "approved_expiry_date"],
        unique=False,
    )

    op.create_table(
        "policy_exception_approvals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("exception_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("decision_reason", sa.Text(), nullable=False),
        sa.Column("approved_expiry_date", sa.Date(), nullable=True),
        sa.Column("conditions", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "decision IN ('approved', 'rejected')",
            name="ck_policy_exception_approvals_decision",
        ),
        sa.CheckConstraint(
            "(decision = 'approved' AND approved_expiry_date IS NOT NULL) OR (decision = 'rejected' AND approved_expiry_date IS NULL)",
            name="ck_policy_exception_approvals_decision_expiry_consistency",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["exception_id"], ["policy_exceptions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("exception_id", name="uq_policy_exception_approvals_exception_id"),
    )
    op.create_index(
        "ix_policy_exception_approvals_organization_id",
        "policy_exception_approvals",
        ["organization_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_policy_exception_approvals_organization_id", table_name="policy_exception_approvals")
    op.drop_table("policy_exception_approvals")

    op.drop_index("ix_policy_exceptions_org_status_approved_expiry", table_name="policy_exceptions")
    op.drop_index("ix_policy_exceptions_org_requested_by", table_name="policy_exceptions")
    op.drop_index("ix_policy_exceptions_org_status", table_name="policy_exceptions")
    op.drop_index("ix_policy_exceptions_org_policy", table_name="policy_exceptions")
    op.drop_index("ix_policy_exceptions_organization_id", table_name="policy_exceptions")
    op.drop_table("policy_exceptions")
