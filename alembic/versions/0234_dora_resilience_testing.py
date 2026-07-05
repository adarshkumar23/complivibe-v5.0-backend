"""add DORA resilience testing records

Cadence rules: Regulation (EU) 2022/2554 (DORA), Articles 24 and 26; Joint
RTS on Threat-Led Penetration Testing, Commission Delegated Regulation
(EU) 2025/1190.

Revision ID: 0234_dora_resilience_testing
Revises: 0233_risk_quantification
Create Date: 2026-07-05 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "0234_dora_resilience_testing"
down_revision: str | None = "0233_risk_quantification"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSIONS = [
    (
        "resilience_testing:read",
        "Read DORA resilience test records and overdue-test status",
        ("owner", "admin", "compliance_manager", "reviewer", "auditor", "readonly"),
    ),
    (
        "resilience_testing:manage",
        "Create and update DORA resilience test records",
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
        "resilience_tests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("test_type", sa.String(length=32), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("scheduled_date", sa.Date(), nullable=False),
        sa.Column("completed_date", sa.Date(), nullable=True),
        sa.Column("results_json", sa.JSON(), nullable=True),
        sa.Column("findings_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="scheduled"),
        sa.Column("owner_team", sa.String(length=255), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "test_type IN ('tabletop', 'simulation', 'threat_led_pen_test')",
            name="ck_resilience_tests_test_type",
        ),
        sa.CheckConstraint(
            "status IN ('scheduled', 'in_progress', 'completed', 'cancelled')",
            name="ck_resilience_tests_status",
        ),
        sa.CheckConstraint(
            "findings_count >= 0",
            name="ck_resilience_tests_findings_count_nonneg",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_resilience_tests_org_type_scheduled",
        "resilience_tests",
        ["organization_id", "test_type", "scheduled_date"],
        unique=False,
    )
    op.create_index(
        "ix_resilience_tests_org_status",
        "resilience_tests",
        ["organization_id", "status"],
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

    op.drop_index("ix_resilience_tests_org_status", table_name="resilience_tests")
    op.drop_index("ix_resilience_tests_org_type_scheduled", table_name="resilience_tests")
    op.drop_table("resilience_tests")
