"""nis2 dora sla wiring

Revision ID: 0151_nis2_dora_sla_wiring
Revises: 0150_nis2_seed
Create Date: 2026-06-27 15:40:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0151_nis2_dora_sla_wiring"
down_revision: str | None = "0150_nis2_seed"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_column(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    if not inspector.has_table(table_name):
        return False
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def _has_constraint(inspector: sa.Inspector, table_name: str, constraint_name: str) -> bool:
    if not inspector.has_table(table_name):
        return False
    return any(item.get("name") == constraint_name for item in inspector.get_check_constraints(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("breach_notifications"):
        return

    if not _has_column(inspector, "breach_notifications", "regulatory_framework"):
        op.add_column("breach_notifications", sa.Column("regulatory_framework", sa.String(length=50), nullable=True))
        inspector = sa.inspect(bind)

    op.alter_column("breach_notifications", "regulatory_framework", existing_type=sa.String(length=50), nullable=True)

    ck_name = "ck_breach_notifications_regulatory_framework"
    if _has_constraint(inspector, "breach_notifications", ck_name):
        op.drop_constraint(ck_name, "breach_notifications", type_="check")

    op.create_check_constraint(
        ck_name,
        "breach_notifications",
        "regulatory_framework IN ('gdpr', 'dora', 'nis2', 'hipaa', 'ccpa', 'dpdp') OR regulatory_framework IS NULL",
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("breach_notifications") or not _has_column(inspector, "breach_notifications", "regulatory_framework"):
        return

    ck_name = "ck_breach_notifications_regulatory_framework"
    if _has_constraint(inspector, "breach_notifications", ck_name):
        op.drop_constraint(ck_name, "breach_notifications", type_="check")

    op.create_check_constraint(
        ck_name,
        "breach_notifications",
        "regulatory_framework IN ('gdpr', 'hipaa', 'ccpa', 'dpdp', 'pci_dss', 'custom')",
    )
    op.execute("UPDATE breach_notifications SET regulatory_framework = 'gdpr' WHERE regulatory_framework IS NULL")
    op.alter_column(
        "breach_notifications",
        "regulatory_framework",
        existing_type=sa.String(length=50),
        nullable=False,
        existing_server_default=sa.text("'gdpr'"),
    )
