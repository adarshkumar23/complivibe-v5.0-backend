"""add business continuity management (BCM/BIA)

Revision ID: 0231_business_continuity_management
Revises: 0230_vendor_remediation_portal
Create Date: 2026-07-05 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "0231_business_continuity_management"
down_revision: str | None = "0230_vendor_remediation_portal"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSIONS = [
    (
        "bcm:read",
        "Read business continuity processes and BIA assessments",
        ("owner", "admin", "compliance_manager", "reviewer", "auditor", "readonly"),
    ),
    (
        "bcm:manage",
        "Create and update business continuity processes and BIA assessments",
        ("owner", "admin", "compliance_manager"),
    ),
]


def _ensure_permissions() -> None:
    bind = op.get_bind()
    for key, description, roles in PERMISSIONS:
        permission_id = bind.execute(sa.text("SELECT id FROM permissions WHERE key = :key"), {"key": key}).scalar()
        if permission_id is None:
            permission_id = bind.execute(
                sa.text("INSERT INTO permissions (id, key, description) VALUES (:id, :key, :description) RETURNING id"),
                {"id": str(uuid.uuid4()), "key": key, "description": description},
            ).scalar_one()

        role_ids = bind.execute(
            sa.text(f"SELECT id FROM roles WHERE name IN ({','.join(':r' + str(i) for i in range(len(roles)))}) AND is_active = TRUE"),
            {f"r{i}": name for i, name in enumerate(roles)},
        ).scalars().all()
        for role_id in role_ids:
            exists = bind.execute(
                sa.text("SELECT 1 FROM role_permissions WHERE role_id = :role_id AND permission_id = :permission_id"),
                {"role_id": role_id, "permission_id": permission_id},
            ).scalar()
            if exists is None:
                bind.execute(
                    sa.text("INSERT INTO role_permissions (id, role_id, permission_id) VALUES (:id, :role_id, :permission_id)"),
                    {"id": str(uuid.uuid4()), "role_id": role_id, "permission_id": permission_id},
                )


def upgrade() -> None:
    op.create_table(
        "business_processes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("criticality_tier", sa.String(length=32), nullable=False, server_default="tier_3_standard"),
        sa.Column("recovery_time_objective_hours", sa.Integer(), nullable=False),
        sa.Column("recovery_point_objective_hours", sa.Integer(), nullable=False),
        sa.Column("dependencies_json", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "criticality_tier IN ('tier_1_critical', 'tier_2_high', 'tier_3_standard')",
            name="ck_business_processes_criticality_tier",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'archived')",
            name="ck_business_processes_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_business_processes_org_criticality",
        "business_processes",
        ["organization_id", "criticality_tier"],
        unique=False,
    )

    op.create_table(
        "bia_assessments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("process_id", sa.Uuid(), nullable=False),
        sa.Column("impact_analysis_json", sa.JSON(), nullable=False),
        sa.Column("financial_impact_tier", sa.String(length=32), nullable=True),
        sa.Column("review_frequency_months", sa.Integer(), nullable=False, server_default="12"),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("reviewed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "financial_impact_tier IS NULL OR financial_impact_tier IN ('low', 'medium', 'high', 'severe')",
            name="ck_bia_assessments_financial_impact_tier",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["process_id"], ["business_processes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_bia_assessments_org_process",
        "bia_assessments",
        ["organization_id", "process_id"],
        unique=False,
    )

    _ensure_permissions()


def downgrade() -> None:
    bind = op.get_bind()
    for key, _description, _roles in PERMISSIONS:
        permission_id = bind.execute(sa.text("SELECT id FROM permissions WHERE key = :key"), {"key": key}).scalar()
        if permission_id is not None:
            bind.execute(sa.text("DELETE FROM role_permissions WHERE permission_id = :permission_id"), {"permission_id": permission_id})
            bind.execute(sa.text("DELETE FROM permissions WHERE id = :permission_id"), {"permission_id": permission_id})

    op.drop_index("ix_bia_assessments_org_process", table_name="bia_assessments")
    op.drop_table("bia_assessments")

    op.drop_index("ix_business_processes_org_criticality", table_name="business_processes")
    op.drop_table("business_processes")
