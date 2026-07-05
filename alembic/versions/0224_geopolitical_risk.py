"""add geopolitical risk monitoring

Revision ID: 0224_geopolitical_risk
Revises: 0223_synthetic_datasets
Create Date: 2026-07-05 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "0224_geopolitical_risk"
down_revision: str | None = "0223_synthetic_datasets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSIONS = [
    ("geopolitical_risk:read", "Read geopolitical risk signals, vendor region exposures, and cross-referenced exposure summaries", ("owner", "admin", "compliance_manager", "reviewer", "auditor", "readonly")),
    ("geopolitical_risk:manage", "Trigger geopolitical risk ingestion and manage vendor geopolitical exposure records", ("owner", "admin", "compliance_manager", "reviewer")),
]


def upgrade() -> None:
    op.create_table(
        "geopolitical_risk_signals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("region", sa.String(length=100), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column("headline", sa.Text(), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("source_error", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "category IN ('conflict','sanctions','political_instability','trade_restriction','regulatory_change','other')",
            name="ck_geopolitical_risk_signals_category",
        ),
        sa.CheckConstraint(
            "severity IN ('low','medium','high','critical')",
            name="ck_geopolitical_risk_signals_severity",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_geopolitical_risk_signals_org_region", "geopolitical_risk_signals", ["organization_id", "region"], unique=False)
    op.create_index("ix_geopolitical_risk_signals_org_category", "geopolitical_risk_signals", ["organization_id", "category"], unique=False)
    op.create_index("ix_geopolitical_risk_signals_org_severity", "geopolitical_risk_signals", ["organization_id", "severity"], unique=False)
    op.create_index("ix_geopolitical_risk_signals_org_detected_at", "geopolitical_risk_signals", ["organization_id", "detected_at"], unique=False)

    op.create_table(
        "vendor_geopolitical_exposure",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("vendor_id", sa.Uuid(), nullable=False),
        sa.Column("region", sa.String(length=100), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vendor_geopolitical_exposure_org_vendor", "vendor_geopolitical_exposure", ["organization_id", "vendor_id"], unique=False)
    op.create_index("ix_vendor_geopolitical_exposure_org_region", "vendor_geopolitical_exposure", ["organization_id", "region"], unique=False)

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
    op.drop_table("vendor_geopolitical_exposure")
    op.drop_index("ix_geopolitical_risk_signals_org_detected_at", table_name="geopolitical_risk_signals")
    op.drop_index("ix_geopolitical_risk_signals_org_severity", table_name="geopolitical_risk_signals")
    op.drop_index("ix_geopolitical_risk_signals_org_category", table_name="geopolitical_risk_signals")
    op.drop_index("ix_geopolitical_risk_signals_org_region", table_name="geopolitical_risk_signals")
    op.drop_table("geopolitical_risk_signals")
