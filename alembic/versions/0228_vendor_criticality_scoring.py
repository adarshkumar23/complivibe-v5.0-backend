"""vendor criticality weighted scoring

Revision ID: 0228_vendor_criticality_scoring
Revises: 0228_t13_supply_chain_flags
Create Date: 2026-07-05 00:00:00.000000
"""

from collections.abc import Sequence
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0228_vendor_criticality_scoring"
down_revision: str | None = "0228_t13_supply_chain_flags"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


PERMISSIONS: tuple[tuple[str, str], ...] = (
    ("vendor_criticality:read", "Read vendor business-criticality profiles and scoring settings"),
    ("vendor_criticality:manage", "Manage vendor business-criticality profiles and scoring settings"),
)


def upgrade() -> None:
    op.create_table(
        "vendor_criticality_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revenue_dependency_weight", sa.Numeric(precision=6, scale=4), nullable=False),
        sa.Column("data_volume_weight", sa.Numeric(precision=6, scale=4), nullable=False),
        sa.Column("operational_criticality_weight", sa.Numeric(precision=6, scale=4), nullable=False),
        sa.Column("substitutability_weight", sa.Numeric(precision=6, scale=4), nullable=False),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", name="uq_vendor_criticality_settings_org"),
    )
    op.create_index("ix_vendor_criticality_settings_organization_id", "vendor_criticality_settings", ["organization_id"], unique=False)
    op.create_index("ix_vendor_criticality_settings_org", "vendor_criticality_settings", ["organization_id"], unique=False)

    op.create_table(
        "vendor_criticality_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revenue_dependency_pct", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("data_volume_tier", sa.String(length=32), nullable=False),
        sa.Column("operational_criticality", sa.String(length=32), nullable=False),
        sa.Column("substitutability_score", sa.Integer(), nullable=False),
        sa.Column("criticality_score", sa.Integer(), nullable=False),
        sa.Column("criticality_tier", sa.String(length=32), nullable=False),
        sa.Column("score_explanation_json", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "vendor_id", name="uq_vendor_criticality_profiles_org_vendor"),
    )
    op.create_index("ix_vendor_criticality_profiles_organization_id", "vendor_criticality_profiles", ["organization_id"], unique=False)
    op.create_index("ix_vendor_criticality_profiles_org_vendor", "vendor_criticality_profiles", ["organization_id", "vendor_id"], unique=False)
    op.create_index("ix_vendor_criticality_profiles_org_tier", "vendor_criticality_profiles", ["organization_id", "criticality_tier"], unique=False)
    op.create_index("ix_vendor_criticality_profiles_org_score", "vendor_criticality_profiles", ["organization_id", "criticality_score"], unique=False)

    bind = op.get_bind()
    for key, description in PERMISSIONS:
        permission_id = bind.execute(sa.text("SELECT id FROM permissions WHERE key = :key"), {"key": key}).scalar()
        if permission_id is None:
            permission_id = bind.execute(
                sa.text("INSERT INTO permissions (id, key, description) VALUES (:id, :key, :description) RETURNING id"),
                {"id": str(uuid.uuid4()), "key": key, "description": description},
            ).scalar_one()

        role_names = (
            ("owner", "admin", "compliance_manager")
            if key.endswith(":manage")
            else ("owner", "admin", "compliance_manager", "reviewer", "auditor", "readonly")
        )
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


def downgrade() -> None:
    op.drop_index("ix_vendor_criticality_profiles_org_score", table_name="vendor_criticality_profiles")
    op.drop_index("ix_vendor_criticality_profiles_org_tier", table_name="vendor_criticality_profiles")
    op.drop_index("ix_vendor_criticality_profiles_org_vendor", table_name="vendor_criticality_profiles")
    op.drop_index("ix_vendor_criticality_profiles_organization_id", table_name="vendor_criticality_profiles")
    op.drop_table("vendor_criticality_profiles")

    op.drop_index("ix_vendor_criticality_settings_org", table_name="vendor_criticality_settings")
    op.drop_index("ix_vendor_criticality_settings_organization_id", table_name="vendor_criticality_settings")
    op.drop_table("vendor_criticality_settings")

    permissions_table = sa.table("permissions", sa.column("key", sa.String()))
    for key, _ in PERMISSIONS:
        bind = op.get_bind()
        permission_id = bind.execute(sa.text("SELECT id FROM permissions WHERE key = :key"), {"key": key}).scalar()
        if permission_id is not None:
            bind.execute(sa.text("DELETE FROM role_permissions WHERE permission_id = :permission_id"), {"permission_id": permission_id})
            op.execute(permissions_table.delete().where(permissions_table.c.key == key))
