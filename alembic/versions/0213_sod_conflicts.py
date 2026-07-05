"""add sod conflicts

Revision ID: 0213_sod_conflicts
Revises: 0212_access_certifications
Create Date: 2026-07-05 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0213_sod_conflicts"
down_revision: str | None = "0212_access_certifications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sod_conflict_rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("permission_a", sa.String(length=120), nullable=False),
        sa.Column("permission_b", sa.String(length=120), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sod_conflict_rules_organization_id", "sod_conflict_rules", ["organization_id"], unique=False)
    op.create_index("ix_sod_conflict_rules_permission_a", "sod_conflict_rules", ["permission_a"], unique=False)
    op.create_index("ix_sod_conflict_rules_permission_b", "sod_conflict_rules", ["permission_b"], unique=False)
    op.create_index("ix_sod_conflict_rules_active", "sod_conflict_rules", ["active"], unique=False)
    op.create_index("ix_sod_conflict_rules_status", "sod_conflict_rules", ["status"], unique=False)
    op.create_index("ix_sod_conflict_rules_org_status", "sod_conflict_rules", ["organization_id", "status"], unique=False)
    op.create_index("ix_sod_conflict_rules_org_permissions", "sod_conflict_rules", ["organization_id", "permission_a", "permission_b"], unique=False)

    op.create_table(
        "sod_conflict_findings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("rule_id", sa.Uuid(), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by", sa.Uuid(), nullable=True),
        sa.Column("waived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("waived_by", sa.Uuid(), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["acknowledged_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["rule_id"], ["sod_conflict_rules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["waived_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sod_conflict_findings_organization_id", "sod_conflict_findings", ["organization_id"], unique=False)
    op.create_index("ix_sod_conflict_findings_user_id", "sod_conflict_findings", ["user_id"], unique=False)
    op.create_index("ix_sod_conflict_findings_rule_id", "sod_conflict_findings", ["rule_id"], unique=False)
    op.create_index("ix_sod_conflict_findings_status", "sod_conflict_findings", ["status"], unique=False)
    op.create_index("ix_sod_conflict_findings_org_status", "sod_conflict_findings", ["organization_id", "status"], unique=False)
    op.create_index("ix_sod_conflict_findings_user_rule_status", "sod_conflict_findings", ["user_id", "rule_id", "status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_sod_conflict_findings_user_rule_status", table_name="sod_conflict_findings")
    op.drop_index("ix_sod_conflict_findings_org_status", table_name="sod_conflict_findings")
    op.drop_index("ix_sod_conflict_findings_status", table_name="sod_conflict_findings")
    op.drop_index("ix_sod_conflict_findings_rule_id", table_name="sod_conflict_findings")
    op.drop_index("ix_sod_conflict_findings_user_id", table_name="sod_conflict_findings")
    op.drop_index("ix_sod_conflict_findings_organization_id", table_name="sod_conflict_findings")
    op.drop_table("sod_conflict_findings")
    op.drop_index("ix_sod_conflict_rules_org_permissions", table_name="sod_conflict_rules")
    op.drop_index("ix_sod_conflict_rules_org_status", table_name="sod_conflict_rules")
    op.drop_index("ix_sod_conflict_rules_status", table_name="sod_conflict_rules")
    op.drop_index("ix_sod_conflict_rules_active", table_name="sod_conflict_rules")
    op.drop_index("ix_sod_conflict_rules_permission_b", table_name="sod_conflict_rules")
    op.drop_index("ix_sod_conflict_rules_permission_a", table_name="sod_conflict_rules")
    op.drop_index("ix_sod_conflict_rules_organization_id", table_name="sod_conflict_rules")
    op.drop_table("sod_conflict_rules")
