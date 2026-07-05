"""vendor concentration risk detection

Revision ID: 0229_vendor_concentration_risk
Revises: 0228_vendor_criticality_scoring
Create Date: 2026-07-05 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "0229_vendor_concentration_risk"
down_revision: str | None = "0228_vendor_criticality_scoring"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSIONS = [
    ("vendor_concentration_risk:read", "Read vendor concentration risk detection and generated risk linkage", ("owner", "admin", "compliance_manager", "reviewer", "auditor", "readonly")),
    ("vendor_concentration_risk:manage", "Recompute vendor concentration risk detection and create linked risk register entries", ("owner", "admin", "compliance_manager", "reviewer")),
]


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
        "vendor_concentration_risk_detections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="below_threshold"),
        sa.Column("hhi_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("threshold_hhi_score", sa.Integer(), nullable=False, server_default="1800"),
        sa.Column("top_vendor_id", sa.Uuid(), nullable=True),
        sa.Column("top_vendor_name", sa.String(length=255), nullable=True),
        sa.Column("top_vendor_share_basis_points", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("exposure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("critical_vendor_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("dependency_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("risk_id", sa.Uuid(), nullable=True),
        sa.Column("convention_source_title", sa.String(length=255), nullable=False),
        sa.Column("convention_source_url", sa.String(length=1000), nullable=False),
        sa.Column("criticality_source_title", sa.String(length=255), nullable=False),
        sa.Column("criticality_source_url", sa.String(length=1000), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=True),
        sa.Column("recomputed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("recomputed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["top_vendor_id"], ["vendors.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["risk_id"], ["risks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["recomputed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", name="uq_vendor_concentration_risk_detection_org"),
    )
    op.create_index("ix_vendor_concentration_risk_org_status", "vendor_concentration_risk_detections", ["organization_id", "status"], unique=False)
    op.create_index("ix_vendor_concentration_risk_org_risk", "vendor_concentration_risk_detections", ["organization_id", "risk_id"], unique=False)

    bind = op.get_bind()
    for key, description, roles in PERMISSIONS:
        permission_id = _ensure_permission(bind, key, description)
        _grant_to_roles(bind, permission_id, roles)


def downgrade() -> None:
    bind = op.get_bind()
    for key, _description, _roles in PERMISSIONS:
        permission_id = bind.execute(sa.text("SELECT id FROM permissions WHERE key = :key"), {"key": key}).scalar()
        if permission_id is not None:
            bind.execute(sa.text("DELETE FROM role_permissions WHERE permission_id = :permission_id"), {"permission_id": permission_id})
            bind.execute(sa.text("DELETE FROM permissions WHERE id = :permission_id"), {"permission_id": permission_id})
    op.drop_index("ix_vendor_concentration_risk_org_risk", table_name="vendor_concentration_risk_detections")
    op.drop_index("ix_vendor_concentration_risk_org_status", table_name="vendor_concentration_risk_detections")
    op.drop_table("vendor_concentration_risk_detections")
