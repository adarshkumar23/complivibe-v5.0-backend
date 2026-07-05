"""add c2pa content provenance records

Revision ID: 0221_content_provenance
Revises: 0220_ip_assets
Create Date: 2026-07-05 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "0221_content_provenance"
down_revision: str | None = "0220_ip_assets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSIONS = [
    ("content_provenance:manage", "Verify and manage content provenance (C2PA manifest) records", ("owner", "admin", "compliance_manager", "reviewer")),
]


def upgrade() -> None:
    op.create_table(
        "content_provenance_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("content_identifier", sa.String(length=500), nullable=False),
        sa.Column("raw_manifest", sa.JSON(), nullable=False),
        sa.Column("verification_status", sa.String(length=20), nullable=False),
        sa.Column("invalid_reason", sa.String(length=50), nullable=True),
        sa.Column("spec_version_detected", sa.String(length=100), nullable=True),
        sa.Column("claim_generator", sa.String(length=255), nullable=True),
        sa.Column("assertion_count", sa.Integer(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "verification_status IN ('valid','invalid')",
            name="ck_content_provenance_records_verification_status",
        ),
        sa.CheckConstraint(
            "invalid_reason IS NULL OR invalid_reason IN ('missing_signature','malformed_claim','unsupported_version','tampered_signature')",
            name="ck_content_provenance_records_invalid_reason",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_content_provenance_records_org_status", "content_provenance_records", ["organization_id", "verification_status"], unique=False)
    op.create_index("ix_content_provenance_records_org_identifier", "content_provenance_records", ["organization_id", "content_identifier"], unique=False)

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
    op.drop_index("ix_content_provenance_records_org_identifier", table_name="content_provenance_records")
    op.drop_index("ix_content_provenance_records_org_status", table_name="content_provenance_records")
    op.drop_table("content_provenance_records")
