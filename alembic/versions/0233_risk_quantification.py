"""add risk quantification runs (Monte Carlo / FAIR)

Revision ID: 0233_risk_quantification
Revises: 0232_crisis_management_playbooks
Create Date: 2026-07-05 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "0233_risk_quantification"
down_revision: str | None = "0232_crisis_management_playbooks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSIONS = [
    (
        "financial_risk:read",
        "Read quantitative risk assessment (Monte Carlo/FAIR) runs",
        ("owner", "admin", "compliance_manager", "reviewer", "auditor", "readonly"),
    ),
    (
        "financial_risk:manage",
        "Run quantitative risk assessments (Monte Carlo/FAIR)",
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
        "risk_quantification_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("risk_id", sa.Uuid(), nullable=False),
        sa.Column("methodology", sa.String(length=32), nullable=False),
        sa.Column("input_parameters_json", sa.JSON(), nullable=False),
        sa.Column("loss_exceedance_curve_json", sa.JSON(), nullable=False),
        sa.Column("expected_annual_loss", sa.Numeric(20, 2), nullable=False),
        sa.Column("confidence_intervals_json", sa.JSON(), nullable=False),
        sa.Column("sensitivity_json", sa.JSON(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("computed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "methodology IN ('monte_carlo', 'fair')",
            name="ck_risk_quantification_runs_methodology",
        ),
        sa.CheckConstraint(
            "expected_annual_loss >= 0",
            name="ck_risk_quantification_runs_expected_annual_loss_nonneg",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["risk_id"], ["risks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["computed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_risk_quantification_runs_org_risk_computed_at",
        "risk_quantification_runs",
        ["organization_id", "risk_id", "computed_at"],
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

    op.drop_index("ix_risk_quantification_runs_org_risk_computed_at", table_name="risk_quantification_runs")
    op.drop_table("risk_quantification_runs")
