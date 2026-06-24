"""control mapping layer

Revision ID: 0006_control_mapping_layer
Revises: 0005_framework_engine_foundation
Create Date: 2026-06-18 02:40:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0006_control_mapping_layer"
down_revision: Union[str, Sequence[str], None] = "0005_framework_engine_foundation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("controls", "code", nullable=True)
    op.alter_column("controls", "status", server_default="not_started")
    op.add_column("controls", sa.Column("control_type", sa.String(length=32), nullable=False, server_default="process"))
    op.add_column("controls", sa.Column("criticality", sa.String(length=16), nullable=False, server_default="medium"))
    op.add_column("controls", sa.Column("testing_procedure", sa.Text(), nullable=True))
    op.add_column("controls", sa.Column("implementation_notes", sa.Text(), nullable=True))
    op.add_column("controls", sa.Column("source", sa.String(length=32), nullable=False, server_default="custom"))
    op.add_column("controls", sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_controls_created_by_user",
        "controls",
        "users",
        ["created_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_controls_owner_user_id", "controls", ["owner_id"], unique=False)

    op.create_table(
        "control_obligation_mappings",
        sa.Column("control_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("obligation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mapping_type", sa.String(length=32), nullable=False, server_default="supports"),
        sa.Column("confidence", sa.String(length=32), nullable=False, server_default="manual_confirmed"),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["control_id"], ["controls.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["obligation_id"], ["obligations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "control_id", "obligation_id", name="uq_control_obligation_mapping"),
    )
    op.create_index("ix_control_obligation_mappings_control_id", "control_obligation_mappings", ["control_id"], unique=False)
    op.create_index("ix_control_obligation_mappings_obligation_id", "control_obligation_mappings", ["obligation_id"], unique=False)
    op.create_index("ix_control_obligation_mappings_organization_id", "control_obligation_mappings", ["organization_id"], unique=False)
    op.create_index("ix_control_obligation_mappings_status", "control_obligation_mappings", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_control_obligation_mappings_status", table_name="control_obligation_mappings")
    op.drop_index("ix_control_obligation_mappings_organization_id", table_name="control_obligation_mappings")
    op.drop_index("ix_control_obligation_mappings_obligation_id", table_name="control_obligation_mappings")
    op.drop_index("ix_control_obligation_mappings_control_id", table_name="control_obligation_mappings")
    op.drop_table("control_obligation_mappings")

    op.drop_index("ix_controls_owner_user_id", table_name="controls")
    op.drop_constraint("fk_controls_created_by_user", "controls", type_="foreignkey")
    op.drop_column("controls", "created_by_user_id")
    op.drop_column("controls", "source")
    op.drop_column("controls", "implementation_notes")
    op.drop_column("controls", "testing_procedure")
    op.drop_column("controls", "criticality")
    op.drop_column("controls", "control_type")
    op.alter_column("controls", "status", server_default="draft")
    op.alter_column("controls", "code", nullable=False)
