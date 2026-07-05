"""add training data rights management

Revision ID: 0222_training_datasets
Revises: 0221_content_provenance
Create Date: 2026-07-05 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "0222_training_datasets"
down_revision: str | None = "0221_content_provenance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSIONS = [
    ("training_data_rights:manage", "Create and manage training dataset rights/provenance records and view rights-gap reports", ("owner", "admin", "compliance_manager", "reviewer")),
]


def upgrade() -> None:
    op.create_table(
        "training_datasets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=500), nullable=True),
        sa.Column("license_type", sa.String(length=32), nullable=False, server_default="unclear"),
        sa.Column("consent_basis", sa.String(length=32), nullable=True),
        sa.Column("linked_ai_system_id", sa.Uuid(), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "license_type IN ('public_domain','creative_commons','commercial_license','proprietary_internal','unclear','none')",
            name="ck_training_datasets_license_type",
        ),
        sa.CheckConstraint(
            "consent_basis IS NULL OR consent_basis IN ('explicit_consent','legitimate_interest','contractual','statutory','not_applicable','unclear')",
            name="ck_training_datasets_consent_basis",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["linked_ai_system_id"], ["ai_systems.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_training_datasets_org_ai_system", "training_datasets", ["organization_id", "linked_ai_system_id"], unique=False)
    op.create_index("ix_training_datasets_org_license_type", "training_datasets", ["organization_id", "license_type"], unique=False)

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
    op.drop_index("ix_training_datasets_org_license_type", table_name="training_datasets")
    op.drop_index("ix_training_datasets_org_ai_system", table_name="training_datasets")
    op.drop_table("training_datasets")
