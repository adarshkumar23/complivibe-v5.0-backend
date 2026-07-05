"""add connector marketplace

Revision ID: 0217_connector_marketplace
Revises: 0216_carbon_accounting
Create Date: 2026-07-05 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "0217_connector_marketplace"
down_revision: str | None = "0216_carbon_accounting"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSIONS = {
    "connectors:read": "Read connector marketplace catalog and organization connector status",
    "connectors:write": "Create connector catalog entries and manage organization connector enablement",
}
DEFAULT_CONNECTORS = [
    ("Carbon accounting file ingest", "sustainability", "CSV or file-based greenhouse gas emissions import.", {"type": "object", "required": ["file_format"], "properties": {"file_format": {"type": "string"}, "scope_mapping": {"type": "object"}}}),
    ("XBRL disclosure export", "reporting", "Structured ESG disclosure export configuration.", {"type": "object", "required": ["taxonomy"], "properties": {"taxonomy": {"type": "string"}, "entity_identifier": {"type": "string"}}}),
    ("Data catalog metadata ingest", "data_governance", "Metadata and lineage ingestion from an external data catalog.", {"type": "object", "properties": {"base_url": {"type": "string"}, "schedule": {"type": "string"}}}),
    ("Access review evidence import", "identity_governance", "Periodic access review evidence import.", {"type": "object", "properties": {"review_frequency": {"type": "string"}, "source_system": {"type": "string"}}}),
]


def _ensure_permission(bind, key: str, description: str):
    permission_id = bind.execute(sa.text("SELECT id FROM permissions WHERE key = :key"), {"key": key}).scalar()
    if permission_id is None:
        permission_id = bind.execute(
            sa.text("INSERT INTO permissions (id, key, description) VALUES (:id, :key, :description) RETURNING id"),
            {"id": str(uuid.uuid4()), "key": key, "description": description},
        ).scalar_one()
    return permission_id


def upgrade() -> None:
    op.create_table(
        "connector_catalog_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("config_schema", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_connector_catalog_entries_name"),
    )
    op.create_index("ix_connector_catalog_entries_category", "connector_catalog_entries", ["category"], unique=False)
    op.create_index("ix_connector_catalog_entries_enabled", "connector_catalog_entries", ["enabled"], unique=False)

    op.create_table(
        "connector_org_enablements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("connector_id", sa.Uuid(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("config_values_json", sa.JSON(), nullable=True),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["connector_id"], ["connector_catalog_entries.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "connector_id", name="uq_connector_enablement_org_connector"),
    )
    op.create_index("ix_connector_org_enablements_organization_id", "connector_org_enablements", ["organization_id"], unique=False)
    op.create_index("ix_connector_enablements_org_enabled", "connector_org_enablements", ["organization_id", "enabled"], unique=False)

    catalog = sa.table(
        "connector_catalog_entries",
        sa.column("id", sa.Uuid()),
        sa.column("name", sa.String()),
        sa.column("category", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("config_schema", sa.JSON()),
        sa.column("enabled", sa.Boolean()),
    )
    for name, category, description, config_schema in DEFAULT_CONNECTORS:
        op.bulk_insert(catalog, [{"id": uuid.uuid4(), "name": name, "category": category, "description": description, "config_schema": config_schema, "enabled": True}])

    bind = op.get_bind()
    for key, description in PERMISSIONS.items():
        permission_id = _ensure_permission(bind, key, description)
        role_ids = bind.execute(sa.text("SELECT id FROM roles WHERE name IN ('owner', 'admin', 'compliance_manager') AND is_active = TRUE")).scalars().all()
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
    for key in PERMISSIONS:
        permission_id = bind.execute(sa.text("SELECT id FROM permissions WHERE key = :key"), {"key": key}).scalar()
        if permission_id is not None:
            bind.execute(sa.text("DELETE FROM role_permissions WHERE permission_id = :permission_id"), {"permission_id": permission_id})
            bind.execute(sa.text("DELETE FROM permissions WHERE id = :permission_id"), {"permission_id": permission_id})
    op.drop_index("ix_connector_enablements_org_enabled", table_name="connector_org_enablements")
    op.drop_index("ix_connector_org_enablements_organization_id", table_name="connector_org_enablements")
    op.drop_table("connector_org_enablements")
    op.drop_index("ix_connector_catalog_entries_enabled", table_name="connector_catalog_entries")
    op.drop_index("ix_connector_catalog_entries_category", table_name="connector_catalog_entries")
    op.drop_table("connector_catalog_entries")
