"""add SAML assertion replay protection

Revision ID: 0245_saml_replay
Revises: 0244_fair_bayesian
Create Date: 2026-07-06 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0245_saml_replay"
down_revision: str | None = "0244_fair_bayesian"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "saml_assertion_replays",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("sso_config_id", sa.Uuid(), nullable=False),
        sa.Column("assertion_id", sa.String(length=255), nullable=False),
        sa.Column("name_id", sa.String(length=320), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sso_config_id"], ["sso_configs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_saml_assertion_replays_org_assertion", "saml_assertion_replays", ["organization_id", "assertion_id"], unique=True)
    op.create_index("ix_saml_assertion_replays_org_expires", "saml_assertion_replays", ["organization_id", "expires_at"], unique=False)
    op.create_index(op.f("ix_saml_assertion_replays_organization_id"), "saml_assertion_replays", ["organization_id"], unique=False)
    op.create_index(op.f("ix_saml_assertion_replays_sso_config_id"), "saml_assertion_replays", ["sso_config_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_saml_assertion_replays_sso_config_id"), table_name="saml_assertion_replays")
    op.drop_index(op.f("ix_saml_assertion_replays_organization_id"), table_name="saml_assertion_replays")
    op.drop_index("ix_saml_assertion_replays_org_expires", table_name="saml_assertion_replays")
    op.drop_index("ix_saml_assertion_replays_org_assertion", table_name="saml_assertion_replays")
    op.drop_table("saml_assertion_replays")
