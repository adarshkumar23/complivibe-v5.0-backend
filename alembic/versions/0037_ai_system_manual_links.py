"""ai system manual links

Revision ID: 0037_ai_system_manual_links
Revises: 0036_ai_system_inventory_foundation
Create Date: 2026-06-19 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0037_ai_system_manual_links"
down_revision: str | None = "0036_ai_system_inventory_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_system_control_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ai_system_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("control_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("link_reason", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("unlinked_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("unlinked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unlink_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["control_id"], ["controls.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["unlinked_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "ai_system_id", "control_id", name="uq_ai_system_control_link"),
    )
    op.create_index(
        "ix_ai_system_control_links_ai_system_id",
        "ai_system_control_links",
        ["ai_system_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_system_control_links_control_id",
        "ai_system_control_links",
        ["control_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_system_control_links_organization_id",
        "ai_system_control_links",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_system_control_links_status",
        "ai_system_control_links",
        ["status"],
        unique=False,
    )

    op.create_table(
        "ai_system_evidence_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ai_system_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("link_reason", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("unlinked_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("unlinked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unlink_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["unlinked_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "ai_system_id", "evidence_id", name="uq_ai_system_evidence_link"),
    )
    op.create_index(
        "ix_ai_system_evidence_links_ai_system_id",
        "ai_system_evidence_links",
        ["ai_system_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_system_evidence_links_evidence_id",
        "ai_system_evidence_links",
        ["evidence_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_system_evidence_links_organization_id",
        "ai_system_evidence_links",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_system_evidence_links_status",
        "ai_system_evidence_links",
        ["status"],
        unique=False,
    )

    op.create_table(
        "ai_system_risk_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ai_system_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("risk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("link_reason", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("unlinked_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("unlinked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unlink_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["risk_id"], ["risks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["unlinked_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "ai_system_id", "risk_id", name="uq_ai_system_risk_link"),
    )
    op.create_index(
        "ix_ai_system_risk_links_ai_system_id",
        "ai_system_risk_links",
        ["ai_system_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_system_risk_links_organization_id",
        "ai_system_risk_links",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_system_risk_links_risk_id",
        "ai_system_risk_links",
        ["risk_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_system_risk_links_status",
        "ai_system_risk_links",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ai_system_risk_links_status", table_name="ai_system_risk_links")
    op.drop_index("ix_ai_system_risk_links_risk_id", table_name="ai_system_risk_links")
    op.drop_index("ix_ai_system_risk_links_organization_id", table_name="ai_system_risk_links")
    op.drop_index("ix_ai_system_risk_links_ai_system_id", table_name="ai_system_risk_links")
    op.drop_table("ai_system_risk_links")

    op.drop_index("ix_ai_system_evidence_links_status", table_name="ai_system_evidence_links")
    op.drop_index("ix_ai_system_evidence_links_organization_id", table_name="ai_system_evidence_links")
    op.drop_index("ix_ai_system_evidence_links_evidence_id", table_name="ai_system_evidence_links")
    op.drop_index("ix_ai_system_evidence_links_ai_system_id", table_name="ai_system_evidence_links")
    op.drop_table("ai_system_evidence_links")

    op.drop_index("ix_ai_system_control_links_status", table_name="ai_system_control_links")
    op.drop_index("ix_ai_system_control_links_organization_id", table_name="ai_system_control_links")
    op.drop_index("ix_ai_system_control_links_control_id", table_name="ai_system_control_links")
    op.drop_index("ix_ai_system_control_links_ai_system_id", table_name="ai_system_control_links")
    op.drop_table("ai_system_control_links")
