"""custom roles extend roles table

Revision ID: 0195_custom_roles_extend_roles_table
Revises: 0194_inbound_questionnaire_response_time_metrics
Create Date: 2026-07-02 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0195_custom_roles_extend_roles_table"
down_revision: str | None = "0194_inbound_questionnaire_response_time_metrics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "roles",
        sa.Column("is_system_role", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "roles",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.alter_column("roles", "organization_id", existing_type=sa.Uuid(), nullable=True)
    op.execute("UPDATE roles SET is_system_role = COALESCE(is_system, true)")
    op.create_index(
        "ix_roles_org_system_active",
        "roles",
        ["organization_id", "is_system_role", "is_active"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_roles_org_system_active", table_name="roles")
    op.execute("UPDATE roles SET organization_id = organization_id WHERE organization_id IS NOT NULL")
    op.alter_column("roles", "organization_id", existing_type=sa.Uuid(), nullable=False)
    op.drop_column("roles", "is_active")
    op.drop_column("roles", "is_system_role")
