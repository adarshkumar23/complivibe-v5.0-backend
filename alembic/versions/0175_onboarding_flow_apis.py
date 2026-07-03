"""onboarding flow apis

Revision ID: 0175_onboarding_flow_apis
Revises: 0174_org_email_configs_ses_delivery
Create Date: 2026-06-30 00:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0175_onboarding_flow_apis"
down_revision: str | None = "0174_org_email_configs_ses_delivery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_table(inspector: sa.Inspector, table_name: str) -> bool:
    return inspector.has_table(table_name)


def _has_column(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    if not inspector.has_table(table_name):
        return False
    return any(col.get("name") == column_name for col in inspector.get_columns(table_name))


def _has_index(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    if not inspector.has_table(table_name):
        return False
    return any(idx.get("name") == index_name for idx in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "organizations"):
        org_columns: list[tuple[str, sa.Column]] = [
            (
                "onboarding_completed",
                sa.Column("onboarding_completed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            ),
            (
                "onboarding_completed_at",
                sa.Column("onboarding_completed_at", sa.DateTime(timezone=True), nullable=True),
            ),
            (
                "onboarding_step",
                sa.Column(
                    "onboarding_step",
                    sa.VARCHAR(length=30),
                    nullable=True,
                    server_default=sa.text("'not_started'"),
                ),
            ),
        ]

        for col_name, col in org_columns:
            if not _has_column(inspector, "organizations", col_name):
                op.add_column("organizations", col)
                inspector = sa.inspect(bind)

    inspector = sa.inspect(bind)
    if not _has_table(inspector, "team_invitations"):
        op.create_table(
            "team_invitations",
            sa.Column("id", sa.Uuid(), nullable=False, server_default=sa.text("gen_random_uuid()")),
            sa.Column("organization_id", sa.Uuid(), nullable=False),
            sa.Column("email", sa.VARCHAR(length=255), nullable=False),
            sa.Column("role_code", sa.VARCHAR(length=30), nullable=False, server_default=sa.text("'member'")),
            sa.Column("invited_by", sa.Uuid(), nullable=False),
            sa.Column("token", sa.VARCHAR(length=128), nullable=False),
            sa.Column("status", sa.VARCHAR(length=20), nullable=False, server_default=sa.text("'pending'")),
            sa.Column(
                "expires_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now() + interval '7 days'"),
            ),
            sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["invited_by"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("token", name="uq_team_inv_token"),
        )

    inspector = sa.inspect(bind)
    if _has_table(inspector, "team_invitations"):
        if not _has_index(inspector, "team_invitations", "ix_team_inv_token"):
            op.create_index("ix_team_inv_token", "team_invitations", ["token"], unique=False)
        inspector = sa.inspect(bind)
        if not _has_index(inspector, "team_invitations", "ix_team_inv_org_status"):
            op.create_index("ix_team_inv_org_status", "team_invitations", ["organization_id", "status"], unique=False)
        inspector = sa.inspect(bind)
        if not _has_index(inspector, "team_invitations", "ux_team_inv_pending_email"):
            op.create_index(
                "ux_team_inv_pending_email",
                "team_invitations",
                ["organization_id", "email"],
                unique=True,
                postgresql_where=sa.text("status = 'pending'"),
                sqlite_where=sa.text("status = 'pending'"),
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "team_invitations"):
        if _has_index(inspector, "team_invitations", "ux_team_inv_pending_email"):
            op.drop_index("ux_team_inv_pending_email", table_name="team_invitations")
        inspector = sa.inspect(bind)
        if _has_index(inspector, "team_invitations", "ix_team_inv_org_status"):
            op.drop_index("ix_team_inv_org_status", table_name="team_invitations")
        inspector = sa.inspect(bind)
        if _has_index(inspector, "team_invitations", "ix_team_inv_token"):
            op.drop_index("ix_team_inv_token", table_name="team_invitations")
        op.drop_table("team_invitations")

    inspector = sa.inspect(bind)
    if _has_table(inspector, "organizations"):
        for col_name in ["onboarding_step", "onboarding_completed_at", "onboarding_completed"]:
            inspector = sa.inspect(bind)
            if _has_column(inspector, "organizations", col_name):
                op.drop_column("organizations", col_name)
