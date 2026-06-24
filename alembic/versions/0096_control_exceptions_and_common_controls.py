"""control exceptions and common controls

Revision ID: 0096_control_exceptions_and_common_controls
Revises: 0095_entity_level_risk_scoring
Create Date: 2026-06-23 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0096_control_exceptions_and_common_controls"
down_revision: str | None = "0095_entity_level_risk_scoring"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "control_exceptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("control_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("exception_type", sa.String(length=50), nullable=False),
        sa.Column("risk_acceptance_reason", sa.Text(), nullable=False),
        sa.Column("compensating_control_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("compensating_description", sa.Text(), nullable=True),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=30), server_default=sa.text("'pending_approval'"), nullable=False),
        sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("revoked_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.Text(), nullable=True),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("review_date", sa.Date(), nullable=True),
        sa.Column("auto_expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tags_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "exception_type IN ('temporary', 'permanent', 'conditional')",
            name="ck_control_exceptions_exception_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending_approval', 'approved', 'rejected', 'active', 'expired', 'revoked', 'cancelled')",
            name="ck_control_exceptions_status",
        ),
        sa.CheckConstraint(
            "expiry_date IS NULL OR expiry_date > effective_date",
            name="ck_control_exceptions_expiry_after_effective",
        ),
        sa.CheckConstraint(
            "(exception_type = 'permanent' AND expiry_date IS NULL) OR (exception_type IN ('temporary', 'conditional') AND expiry_date IS NOT NULL)",
            name="ck_control_exceptions_type_expiry_consistency",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["control_id"], ["controls.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["compensating_control_id"], ["controls.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["rejected_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["revoked_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_control_exceptions_organization_id", "control_exceptions", ["organization_id"], unique=False)
    op.create_index("ix_control_exceptions_org_control", "control_exceptions", ["organization_id", "control_id"], unique=False)
    op.create_index("ix_control_exceptions_org_status", "control_exceptions", ["organization_id", "status"], unique=False)
    op.create_index("ix_control_exceptions_org_expiry", "control_exceptions", ["organization_id", "expiry_date"], unique=False)
    op.create_index("ix_control_exceptions_org_owner", "control_exceptions", ["organization_id", "owner_user_id"], unique=False)

    op.create_table(
        "control_exception_approvals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("exception_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approver_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence", sa.SmallInteger(), server_default=sa.text("1"), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("decision_notes", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'skipped')",
            name="ck_control_exception_approvals_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["exception_id"], ["control_exceptions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["approver_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_control_exception_approvals_organization_id", "control_exception_approvals", ["organization_id"], unique=False)
    op.create_index(
        "ix_control_exception_approvals_exception_sequence",
        "control_exception_approvals",
        ["exception_id", "sequence"],
        unique=False,
    )
    op.create_index(
        "ix_control_exception_approvals_org_approver_status",
        "control_exception_approvals",
        ["organization_id", "approver_user_id", "status"],
        unique=False,
    )

    op.create_table(
        "common_control_mappings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("control_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("framework_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("obligation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("section_reference", sa.String(length=100), nullable=True),
        sa.Column("mapping_rationale", sa.Text(), nullable=True),
        sa.Column("mapping_strength", sa.String(length=20), server_default=sa.text("'full'"), nullable=False),
        sa.Column("verified_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'active'"), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "mapping_strength IN ('full', 'partial', 'compensating')",
            name="ck_common_control_mappings_strength",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'inactive', 'under_review')",
            name="ck_common_control_mappings_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["control_id"], ["controls.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["framework_id"], ["frameworks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["obligation_id"], ["obligations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["verified_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "control_id",
            "framework_id",
            "obligation_id",
            name="uq_common_control_mappings_pair",
        ),
    )
    op.create_index("ix_common_control_mappings_organization_id", "common_control_mappings", ["organization_id"], unique=False)
    op.create_index("ix_common_control_mappings_org_control", "common_control_mappings", ["organization_id", "control_id"], unique=False)
    op.create_index("ix_common_control_mappings_org_framework", "common_control_mappings", ["organization_id", "framework_id"], unique=False)
    op.create_index("ix_common_control_mappings_org_obligation", "common_control_mappings", ["organization_id", "obligation_id"], unique=False)
    op.create_index("ix_common_control_mappings_org_status", "common_control_mappings", ["organization_id", "status"], unique=False)

    op.create_table(
        "common_control_evidence_coverage",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("control_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mapping_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("coverage_status", sa.String(length=20), nullable=False),
        sa.Column("coverage_notes", sa.Text(), nullable=True),
        sa.Column("assessed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "coverage_status IN ('covers', 'partial', 'insufficient')",
            name="ck_common_control_evidence_coverage_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["control_id"], ["controls.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["mapping_id"], ["common_control_mappings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assessed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "control_id",
            "evidence_id",
            "mapping_id",
            name="uq_common_control_evidence_coverage",
        ),
    )
    op.create_index(
        "ix_common_control_evidence_coverage_organization_id",
        "common_control_evidence_coverage",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_common_control_evidence_coverage_org_control",
        "common_control_evidence_coverage",
        ["organization_id", "control_id"],
        unique=False,
    )
    op.create_index(
        "ix_common_control_evidence_coverage_org_evidence",
        "common_control_evidence_coverage",
        ["organization_id", "evidence_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_common_control_evidence_coverage_org_evidence", table_name="common_control_evidence_coverage")
    op.drop_index("ix_common_control_evidence_coverage_org_control", table_name="common_control_evidence_coverage")
    op.drop_index("ix_common_control_evidence_coverage_organization_id", table_name="common_control_evidence_coverage")
    op.drop_table("common_control_evidence_coverage")

    op.drop_index("ix_common_control_mappings_org_status", table_name="common_control_mappings")
    op.drop_index("ix_common_control_mappings_org_obligation", table_name="common_control_mappings")
    op.drop_index("ix_common_control_mappings_org_framework", table_name="common_control_mappings")
    op.drop_index("ix_common_control_mappings_org_control", table_name="common_control_mappings")
    op.drop_index("ix_common_control_mappings_organization_id", table_name="common_control_mappings")
    op.drop_table("common_control_mappings")

    op.drop_index("ix_control_exception_approvals_org_approver_status", table_name="control_exception_approvals")
    op.drop_index("ix_control_exception_approvals_exception_sequence", table_name="control_exception_approvals")
    op.drop_index("ix_control_exception_approvals_organization_id", table_name="control_exception_approvals")
    op.drop_table("control_exception_approvals")

    op.drop_index("ix_control_exceptions_org_owner", table_name="control_exceptions")
    op.drop_index("ix_control_exceptions_org_expiry", table_name="control_exceptions")
    op.drop_index("ix_control_exceptions_org_status", table_name="control_exceptions")
    op.drop_index("ix_control_exceptions_org_control", table_name="control_exceptions")
    op.drop_index("ix_control_exceptions_organization_id", table_name="control_exceptions")
    op.drop_table("control_exceptions")
