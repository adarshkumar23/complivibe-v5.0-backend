"""add vendor remediation portal tokens

Revision ID: 0230_vendor_remediation_portal
Revises: 0229_vendor_concentration_risk
Create Date: 2026-07-05 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "0230_vendor_remediation_portal"
down_revision: str | None = "0229_vendor_concentration_risk"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSIONS = [
    (
        "vendor_remediation_portal:read",
        "Read vendor remediation portal tokens and access metadata",
        ("owner", "admin", "compliance_manager", "reviewer", "auditor", "readonly"),
    ),
    (
        "vendor_remediation_portal:manage",
        "Create and revoke vendor remediation portal tokens",
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
        "vendor_remediation_portal_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("vendor_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("vendor_contact_email", sa.String(length=320), nullable=False),
        sa.Column("vendor_contact_name", sa.String(length=255), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("scoped_action_ids", sa.JSON(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("first_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("access_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'revoked', 'expired')",
            name="ck_vendor_remediation_portal_tokens_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["case_id"], ["vendor_mitigation_cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["revoked_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_vendor_remediation_portal_tokens_token_hash", "vendor_remediation_portal_tokens", ["token_hash"], unique=False)
    op.create_index("ix_vendor_remediation_portal_tokens_org_vendor", "vendor_remediation_portal_tokens", ["organization_id", "vendor_id"], unique=False)
    op.create_index("ix_vendor_remediation_portal_tokens_org_case", "vendor_remediation_portal_tokens", ["organization_id", "case_id"], unique=False)
    op.create_index("ix_vendor_remediation_portal_tokens_org_status", "vendor_remediation_portal_tokens", ["organization_id", "status"], unique=False)
    _ensure_permissions()


def downgrade() -> None:
    bind = op.get_bind()
    for key, _description, _roles in PERMISSIONS:
        permission_id = bind.execute(sa.text("SELECT id FROM permissions WHERE key = :key"), {"key": key}).scalar()
        if permission_id is not None:
            bind.execute(sa.text("DELETE FROM role_permissions WHERE permission_id = :permission_id"), {"permission_id": permission_id})
            bind.execute(sa.text("DELETE FROM permissions WHERE id = :permission_id"), {"permission_id": permission_id})
    op.drop_index("ix_vendor_remediation_portal_tokens_org_status", table_name="vendor_remediation_portal_tokens")
    op.drop_index("ix_vendor_remediation_portal_tokens_org_case", table_name="vendor_remediation_portal_tokens")
    op.drop_index("ix_vendor_remediation_portal_tokens_org_vendor", table_name="vendor_remediation_portal_tokens")
    op.drop_index("ix_vendor_remediation_portal_tokens_token_hash", table_name="vendor_remediation_portal_tokens")
    op.drop_table("vendor_remediation_portal_tokens")
