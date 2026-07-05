"""vendor supply chain visibility

Revision ID: 0218_vendor_supply_chain
Revises: 0217_connector_marketplace
Create Date: 2026-07-05 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "0218_vendor_supply_chain"
down_revision: str | None = "0217_connector_marketplace"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSIONS = {
    "vendor_supply_chain:read": "Read vendor nth-party supply-chain graphs and propagated risk alerts",
    "vendor_supply_chain:manage": "Create and manage vendor nth-party supply-chain links",
}


def _ensure_permission(bind, key: str, description: str):
    permission_id = bind.execute(sa.text("SELECT id FROM permissions WHERE key = :key"), {"key": key}).scalar()
    if permission_id is None:
        permission_id = bind.execute(
            sa.text("INSERT INTO permissions (id, key, description) VALUES (:id, :key, :description) RETURNING id"),
            {"id": str(uuid.uuid4()), "key": key, "description": description},
        ).scalar_one()
    return permission_id


def _grant_to_roles(bind, permission_id, role_names: tuple[str, ...]) -> None:
    role_ids = bind.execute(
        sa.text("SELECT id FROM roles WHERE name IN :names AND is_active = TRUE").bindparams(sa.bindparam("names", expanding=True)),
        {"names": role_names},
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
        "vendor_supply_chain_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("parent_vendor_id", sa.Uuid(), nullable=False),
        sa.Column("sub_vendor_id", sa.Uuid(), nullable=False),
        sa.Column("relationship_type", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deactivated_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["deactivated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_vendor_id"], ["vendors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sub_vendor_id"], ["vendors.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "parent_vendor_id", "sub_vendor_id", "relationship_type", "is_active", name="uq_vendor_supply_chain_active_link"),
    )
    op.create_index("ix_vendor_supply_chain_parent", "vendor_supply_chain_links", ["organization_id", "parent_vendor_id", "is_active"], unique=False)
    op.create_index("ix_vendor_supply_chain_sub", "vendor_supply_chain_links", ["organization_id", "sub_vendor_id", "is_active"], unique=False)

    op.create_table(
        "vendor_supply_chain_alerts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("parent_vendor_id", sa.Uuid(), nullable=False),
        sa.Column("triggering_vendor_id", sa.Uuid(), nullable=False),
        sa.Column("signal_type", sa.String(length=80), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False, server_default="medium"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("source_entity_type", sa.String(length=80), nullable=True),
        sa.Column("source_entity_id", sa.Uuid(), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_vendor_id"], ["vendors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["triggering_vendor_id"], ["vendors.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vendor_supply_chain_alerts_org_parent", "vendor_supply_chain_alerts", ["organization_id", "parent_vendor_id", "status"], unique=False)
    op.create_index("ix_vendor_supply_chain_alerts_org_trigger", "vendor_supply_chain_alerts", ["organization_id", "triggering_vendor_id", "signal_type"], unique=False)

    bind = op.get_bind()
    for key, description in PERMISSIONS.items():
        permission_id = _ensure_permission(bind, key, description)
        roles = ("owner", "admin", "compliance_manager", "reviewer") if key.endswith(":manage") else ("owner", "admin", "compliance_manager", "reviewer", "auditor", "readonly")
        _grant_to_roles(bind, permission_id, roles)


def downgrade() -> None:
    bind = op.get_bind()
    for key in PERMISSIONS:
        permission_id = bind.execute(sa.text("SELECT id FROM permissions WHERE key = :key"), {"key": key}).scalar()
        if permission_id is not None:
            bind.execute(sa.text("DELETE FROM role_permissions WHERE permission_id = :permission_id"), {"permission_id": permission_id})
            bind.execute(sa.text("DELETE FROM permissions WHERE id = :permission_id"), {"permission_id": permission_id})
    op.drop_index("ix_vendor_supply_chain_alerts_org_trigger", table_name="vendor_supply_chain_alerts")
    op.drop_index("ix_vendor_supply_chain_alerts_org_parent", table_name="vendor_supply_chain_alerts")
    op.drop_table("vendor_supply_chain_alerts")
    op.drop_index("ix_vendor_supply_chain_sub", table_name="vendor_supply_chain_links")
    op.drop_index("ix_vendor_supply_chain_parent", table_name="vendor_supply_chain_links")
    op.drop_table("vendor_supply_chain_links")
