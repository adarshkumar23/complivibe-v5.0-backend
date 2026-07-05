"""add synthetic data governance

Revision ID: 0223_synthetic_datasets
Revises: 0222_training_datasets
Create Date: 2026-07-05 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "0223_synthetic_datasets"
down_revision: str | None = "0222_training_datasets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSIONS = [
    ("synthetic_data:manage", "Create, update, delete, and validate synthetic datasets, including governance-gap review", ("owner", "admin", "compliance_manager", "reviewer")),
]


def upgrade() -> None:
    op.create_table(
        "synthetic_datasets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("generation_method", sa.String(length=255), nullable=False),
        sa.Column("source_dataset_id", sa.Uuid(), nullable=True),
        sa.Column("privacy_technique", sa.String(length=50), nullable=False, server_default="none"),
        sa.Column("validation_status", sa.String(length=50), nullable=False, server_default="unvalidated"),
        sa.Column("validation_notes", sa.Text(), nullable=True),
        sa.Column("governance_gap_flag", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "privacy_technique IN ('differential_privacy','k_anonymity','none')",
            name="ck_synthetic_datasets_privacy_technique",
        ),
        sa.CheckConstraint(
            "validation_status IN ('unvalidated','validated','failed_validation')",
            name="ck_synthetic_datasets_validation_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_dataset_id"], ["training_datasets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_synthetic_datasets_org_validation_status", "synthetic_datasets", ["organization_id", "validation_status"], unique=False)
    op.create_index("ix_synthetic_datasets_org_privacy_technique", "synthetic_datasets", ["organization_id", "privacy_technique"], unique=False)
    op.create_index("ix_synthetic_datasets_org_gap_flag", "synthetic_datasets", ["organization_id", "governance_gap_flag"], unique=False)

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
    op.drop_index("ix_synthetic_datasets_org_gap_flag", table_name="synthetic_datasets")
    op.drop_index("ix_synthetic_datasets_org_privacy_technique", table_name="synthetic_datasets")
    op.drop_index("ix_synthetic_datasets_org_validation_status", table_name="synthetic_datasets")
    op.drop_table("synthetic_datasets")
