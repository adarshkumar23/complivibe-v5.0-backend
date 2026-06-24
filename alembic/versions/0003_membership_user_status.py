"""add user and membership status

Revision ID: 0003_membership_user_status
Revises: 0002_rbac_and_audit_enhancements
Create Date: 2026-06-18 01:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0003_membership_user_status"
down_revision: Union[str, Sequence[str], None] = "0002_rbac_and_audit_enhancements"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("status", sa.String(length=32), nullable=False, server_default="active"))

    op.add_column(
        "memberships",
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
    )
    op.add_column("memberships", sa.Column("invited_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_memberships_invited_by_users",
        "memberships",
        "users",
        ["invited_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_memberships_status", "memberships", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_memberships_status", table_name="memberships")
    op.drop_constraint("fk_memberships_invited_by_users", "memberships", type_="foreignkey")
    op.drop_column("memberships", "invited_by")
    op.drop_column("memberships", "status")

    op.drop_column("users", "status")
