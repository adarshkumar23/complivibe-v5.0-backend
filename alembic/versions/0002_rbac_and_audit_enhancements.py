"""rbac and audit enhancements

Revision ID: 0002_rbac_and_audit_enhancements
Revises: 0001_initial_foundation
Create Date: 2026-06-18 00:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002_rbac_and_audit_enhancements"
down_revision: Union[str, Sequence[str], None] = "0001_initial_foundation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "role_permissions",
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("permission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["permission_id"], ["permissions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),
    )
    op.create_index("ix_role_permissions_permission_id", "role_permissions", ["permission_id"], unique=False)
    op.create_index("ix_role_permissions_role_id", "role_permissions", ["role_id"], unique=False)

    op.add_column("audit_logs", sa.Column("entity_type", sa.String(length=120), nullable=True))
    op.add_column("audit_logs", sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column(
        "audit_logs",
        sa.Column(
            "before_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "audit_logs",
        sa.Column(
            "after_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column("audit_logs", sa.Column("ip_address", sa.String(length=64), nullable=True))
    op.add_column("audit_logs", sa.Column("user_agent", sa.String(length=512), nullable=True))

    op.execute("UPDATE audit_logs SET entity_type = target_type WHERE entity_type IS NULL")
    op.execute("UPDATE audit_logs SET entity_id = target_id WHERE entity_id IS NULL")

    op.alter_column("audit_logs", "entity_type", nullable=False)

    op.drop_column("audit_logs", "target_type")
    op.drop_column("audit_logs", "target_id")


def downgrade() -> None:
    op.add_column("audit_logs", sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("audit_logs", sa.Column("target_type", sa.String(length=120), nullable=True))

    op.execute("UPDATE audit_logs SET target_type = entity_type WHERE target_type IS NULL")
    op.execute("UPDATE audit_logs SET target_id = entity_id WHERE target_id IS NULL")

    op.alter_column("audit_logs", "target_type", nullable=False)

    op.drop_column("audit_logs", "user_agent")
    op.drop_column("audit_logs", "ip_address")
    op.drop_column("audit_logs", "after_json")
    op.drop_column("audit_logs", "before_json")
    op.drop_column("audit_logs", "entity_id")
    op.drop_column("audit_logs", "entity_type")

    op.drop_index("ix_role_permissions_role_id", table_name="role_permissions")
    op.drop_index("ix_role_permissions_permission_id", table_name="role_permissions")
    op.drop_table("role_permissions")
