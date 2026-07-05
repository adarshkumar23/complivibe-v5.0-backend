"""add export control compliance checks (T4-8)

Grounded methodology: ECCN (Export Control Classification Number) under the
US Commerce Control List (CCL, administered by BIS); items not on the CCL
default to EAR99. Denied/restricted-party lists: BIS Denied Persons List,
BIS Entity List, BIS Unverified List, OFAC SDN List, State Dept AECA
Debarred List -- all merged into the free, public trade.gov Consolidated
Screening List (CSL), https://www.trade.gov/consolidated-screening-list.
License determination is a function of the ECCN's Reason(s) for Control,
the destination country vs. the Commerce Country Chart (EAR Supp. 1 to
Part 738), and/or a positive denied-party screening match. The screening
implementation lives in
app/satellites/tprm_intelligence/export_control_screening.py and reuses
the TPRM sanctions satellite's `SanctionsEntity` denied-party dataset and
matching helpers rather than duplicating them. This is an initial
screening signal, not a final legal export-control determination.

Revision ID: 0237_export_control_compliance
Revises: 0236_bribery_risk_assessment
Create Date: 2026-07-05 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "0237_export_control_compliance"
down_revision: str | None = "0236_bribery_risk_assessment"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# T4-8 is scoped as its own dedicated permission family (not a reuse of
# vendors:read/vendors:write) per phase instructions.
PERMISSIONS = [
    (
        "export_control:read",
        "Read export control classification and denied-party screening results",
        ("owner", "admin", "compliance_manager", "reviewer", "auditor", "readonly"),
    ),
    (
        "export_control:manage",
        "Create and compute export control classification and denied-party screening",
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
        "export_control_checks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("vendor_id", sa.Uuid(), nullable=False),
        sa.Column("item_description", sa.String(length=500), nullable=False),
        sa.Column("eccn", sa.String(length=10), nullable=True),
        sa.Column("hs_code", sa.String(length=20), nullable=True),
        sa.Column("destination_country", sa.String(length=100), nullable=False),
        sa.Column("denied_party_screening_result_json", sa.JSON(), nullable=False),
        sa.Column("license_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("license_determination_basis", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="screened"),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("computed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('screened', 'license_pending', 'cleared', 'blocked')",
            name="ck_export_control_checks_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["computed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_export_control_checks_org_vendor_computed",
        "export_control_checks",
        ["organization_id", "vendor_id", "computed_at"],
        unique=False,
    )

    _ensure_permissions()


def downgrade() -> None:
    bind = op.get_bind()
    for key, _description, _roles in PERMISSIONS:
        permission_id = bind.execute(sa.text("SELECT id FROM permissions WHERE key = :key"), {"key": key}).scalar()
        if permission_id is not None:
            bind.execute(sa.text("DELETE FROM role_permissions WHERE permission_id = :permission_id"), {"permission_id": permission_id})
            bind.execute(sa.text("DELETE FROM permissions WHERE id = :permission_id"), {"permission_id": permission_id})

    op.drop_index("ix_export_control_checks_org_vendor_computed", table_name="export_control_checks")
    op.drop_table("export_control_checks")
