"""add legal matter management

Revision ID: 0219_legal_matters
Revises: 0218_vendor_supply_chain
Create Date: 2026-07-05 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "0219_legal_matters"
down_revision: str | None = "0218_vendor_supply_chain"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSIONS = [
    ("legal_matters:read", "View legal matters, their linked risks/issues, and status", ("owner", "admin", "compliance_manager", "reviewer", "auditor", "readonly")),
    ("legal_matters:write", "Create, update, link/unlink, and close legal matters", ("owner", "admin", "compliance_manager", "reviewer")),
]


def upgrade() -> None:
    op.create_table(
        "legal_matters",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("matter_type", sa.String(length=32), nullable=False, server_default="other"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column("opposing_party", sa.String(length=255), nullable=True),
        sa.Column("outside_counsel", sa.String(length=255), nullable=True),
        sa.Column("budget", sa.Numeric(14, 2), nullable=True),
        sa.Column("related_risk_id", sa.Uuid(), nullable=True),
        sa.Column("related_issue_id", sa.Uuid(), nullable=True),
        sa.Column("risk_severity_at_link", sa.String(length=16), nullable=True),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "matter_type IN ('litigation','regulatory_inquiry','contract_dispute','ip_dispute','employment','other')",
            name="ck_legal_matters_matter_type",
        ),
        sa.CheckConstraint(
            "status IN ('open','in_progress','on_hold','closed')",
            name="ck_legal_matters_status",
        ),
        sa.CheckConstraint(
            "risk_severity_at_link IS NULL OR risk_severity_at_link IN ('low','medium','high','critical')",
            name="ck_legal_matters_risk_severity_at_link",
        ),
        sa.CheckConstraint(
            "budget IS NULL OR budget >= 0",
            name="ck_legal_matters_budget_non_negative",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["related_risk_id"], ["risks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["related_issue_id"], ["issues.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["closed_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_legal_matters_org_status", "legal_matters", ["organization_id", "status"], unique=False)
    op.create_index("ix_legal_matters_org_matter_type", "legal_matters", ["organization_id", "matter_type"], unique=False)
    op.create_index("ix_legal_matters_org_related_risk", "legal_matters", ["organization_id", "related_risk_id"], unique=False)
    op.create_index("ix_legal_matters_org_related_issue", "legal_matters", ["organization_id", "related_issue_id"], unique=False)

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


def downgrade() -> None:
    bind = op.get_bind()
    for key, _description, _roles in PERMISSIONS:
        permission_id = bind.execute(sa.text("SELECT id FROM permissions WHERE key = :key"), {"key": key}).scalar()
        if permission_id is not None:
            bind.execute(sa.text("DELETE FROM role_permissions WHERE permission_id = :permission_id"), {"permission_id": permission_id})
            bind.execute(sa.text("DELETE FROM permissions WHERE id = :permission_id"), {"permission_id": permission_id})
    op.drop_index("ix_legal_matters_org_related_issue", table_name="legal_matters")
    op.drop_index("ix_legal_matters_org_related_risk", table_name="legal_matters")
    op.drop_index("ix_legal_matters_org_matter_type", table_name="legal_matters")
    op.drop_index("ix_legal_matters_org_status", table_name="legal_matters")
    op.drop_table("legal_matters")
