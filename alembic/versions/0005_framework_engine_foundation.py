"""framework engine foundation

Revision ID: 0005_framework_engine_foundation
Revises: 0004_membership_activation_tokens
Create Date: 2026-06-18 02:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0005_framework_engine_foundation"
down_revision: Union[str, Sequence[str], None] = "0004_membership_activation_tokens"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("frameworks", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("frameworks", sa.Column("category", sa.String(length=64), nullable=False, server_default="general"))
    op.add_column("frameworks", sa.Column("jurisdiction", sa.String(length=128), nullable=False, server_default="global"))
    op.add_column("frameworks", sa.Column("authority", sa.String(length=255), nullable=True))
    op.add_column("frameworks", sa.Column("status", sa.String(length=32), nullable=False, server_default="active"))
    op.add_column(
        "frameworks",
        sa.Column("coverage_level", sa.String(length=32), nullable=False, server_default="metadata_only"),
    )
    op.add_column("frameworks", sa.Column("source_url", sa.String(length=512), nullable=True))
    op.add_column("frameworks", sa.Column("effective_date", sa.Date(), nullable=True))

    op.add_column("obligations", sa.Column("reference_code", sa.String(length=128), nullable=True))
    op.add_column("obligations", sa.Column("plain_language_summary", sa.Text(), nullable=True))
    op.add_column("obligations", sa.Column("obligation_type", sa.String(length=64), nullable=True))
    op.add_column("obligations", sa.Column("jurisdiction", sa.String(length=128), nullable=False, server_default="global"))
    op.add_column("obligations", sa.Column("source_url", sa.String(length=512), nullable=True))
    op.add_column("obligations", sa.Column("version", sa.String(length=50), nullable=True))
    op.add_column("obligations", sa.Column("effective_date", sa.Date(), nullable=True))
    op.add_column("obligations", sa.Column("parent_obligation_id", postgresql.UUID(as_uuid=True), nullable=True))

    op.create_foreign_key(
        "fk_obligations_parent_obligation",
        "obligations",
        "obligations",
        ["parent_obligation_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.execute("UPDATE obligations SET reference_code = id::text WHERE reference_code IS NULL")

    op.alter_column("obligations", "organization_id", nullable=True)
    op.alter_column("obligations", "framework_id", nullable=False)
    op.alter_column("obligations", "status", server_default="active")
    op.alter_column("obligations", "reference_code", nullable=False)

    op.create_index("ix_obligations_framework_status", "obligations", ["framework_id", "status"], unique=False)
    op.create_index("ix_obligations_jurisdiction", "obligations", ["jurisdiction"], unique=False)
    op.create_index("ix_obligations_reference_code", "obligations", ["reference_code"], unique=False)

    op.create_table(
        "organization_frameworks",
        sa.Column("framework_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("activated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deactivated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["activated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["deactivated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["framework_id"], ["frameworks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "framework_id", name="uq_org_framework"),
    )
    op.create_index("ix_organization_frameworks_organization_id", "organization_frameworks", ["organization_id"], unique=False)
    op.create_index("ix_organization_frameworks_status", "organization_frameworks", ["status"], unique=False)

    op.create_table(
        "organization_obligation_states",
        sa.Column("obligation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("applicability_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("implementation_status", sa.String(length=32), nullable=False, server_default="not_started"),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("justification", sa.Text(), nullable=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["obligation_id"], ["obligations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "obligation_id", name="uq_org_obligation_state"),
    )
    op.create_index(
        "ix_organization_obligation_states_organization_id",
        "organization_obligation_states",
        ["organization_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_organization_obligation_states_organization_id", table_name="organization_obligation_states")
    op.drop_table("organization_obligation_states")

    op.drop_index("ix_organization_frameworks_status", table_name="organization_frameworks")
    op.drop_index("ix_organization_frameworks_organization_id", table_name="organization_frameworks")
    op.drop_table("organization_frameworks")

    op.drop_index("ix_obligations_reference_code", table_name="obligations")
    op.drop_index("ix_obligations_jurisdiction", table_name="obligations")
    op.drop_index("ix_obligations_framework_status", table_name="obligations")

    op.alter_column("obligations", "reference_code", nullable=True)
    op.alter_column("obligations", "status", server_default="open")
    op.alter_column("obligations", "framework_id", nullable=True)
    op.alter_column("obligations", "organization_id", nullable=False)

    op.drop_constraint("fk_obligations_parent_obligation", "obligations", type_="foreignkey")
    op.drop_column("obligations", "parent_obligation_id")
    op.drop_column("obligations", "effective_date")
    op.drop_column("obligations", "version")
    op.drop_column("obligations", "source_url")
    op.drop_column("obligations", "jurisdiction")
    op.drop_column("obligations", "obligation_type")
    op.drop_column("obligations", "plain_language_summary")
    op.drop_column("obligations", "reference_code")

    op.drop_column("frameworks", "effective_date")
    op.drop_column("frameworks", "source_url")
    op.drop_column("frameworks", "coverage_level")
    op.drop_column("frameworks", "status")
    op.drop_column("frameworks", "authority")
    op.drop_column("frameworks", "jurisdiction")
    op.drop_column("frameworks", "category")
    op.drop_column("frameworks", "description")
