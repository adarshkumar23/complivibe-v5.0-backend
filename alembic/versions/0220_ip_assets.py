"""add ip/model licensing registry

Revision ID: 0220_ip_assets
Revises: 0219_legal_matters
Create Date: 2026-07-05 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "0220_ip_assets"
down_revision: str | None = "0219_legal_matters"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSIONS = [
    ("ip_assets:read", "Read IP and model/dataset licensing registry records and settings", ("owner", "admin", "compliance_manager", "reviewer", "auditor", "readonly")),
    ("ip_assets:manage", "Create, update, delete IP/licensing registry records and manage the expiring-soon window", ("owner", "admin", "compliance_manager", "reviewer")),
]


def upgrade() -> None:
    op.create_table(
        "ip_assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("asset_type", sa.String(length=32), nullable=False),
        sa.Column("licensor", sa.String(length=255), nullable=True),
        sa.Column("licensee", sa.String(length=255), nullable=True),
        sa.Column("terms", sa.JSON(), nullable=True),
        sa.Column("expiry_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("linked_ai_system_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "asset_type IN ('patent','trademark','model_license','dataset_license')",
            name="ck_ip_assets_asset_type",
        ),
        sa.CheckConstraint(
            "status IN ('active','expired','terminated','pending_renewal')",
            name="ck_ip_assets_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["linked_ai_system_id"], ["ai_systems.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ip_assets_org_asset_type", "ip_assets", ["organization_id", "asset_type"], unique=False)
    op.create_index("ix_ip_assets_org_expiry_date", "ip_assets", ["organization_id", "expiry_date"], unique=False)
    op.create_index("ix_ip_assets_org_linked_ai_system", "ip_assets", ["organization_id", "linked_ai_system_id"], unique=False)

    op.create_table(
        "ip_asset_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expiring_soon_window_days", sa.Integer(), nullable=False, server_default="90"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", name="uq_ip_asset_settings_organization_id"),
    )

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
    op.drop_table("ip_asset_settings")
    op.drop_index("ix_ip_assets_org_linked_ai_system", table_name="ip_assets")
    op.drop_index("ix_ip_assets_org_expiry_date", table_name="ip_assets")
    op.drop_index("ix_ip_assets_org_asset_type", table_name="ip_assets")
    op.drop_table("ip_assets")
