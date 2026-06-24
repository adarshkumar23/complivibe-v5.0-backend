"""email worker orchestration

Revision ID: 0008_email_worker_orchestration
Revises: 0007_email_outbox_foundation
Create Date: 2026-06-18 10:55:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0008_email_worker_orchestration"
down_revision: Union[str, Sequence[str], None] = "0007_email_outbox_foundation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("email_outbox", sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("email_outbox", sa.Column("locked_by", sa.String(length=120), nullable=True))
    op.add_column("email_outbox", sa.Column("lock_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("email_outbox", sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("email_outbox", sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("email_outbox", sa.Column("dead_lettered_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "email_outbox",
        sa.Column("worker_metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    op.create_index("ix_email_outbox_next_attempt_at", "email_outbox", ["next_attempt_at"], unique=False)
    op.create_index("ix_email_outbox_lock_expires_at", "email_outbox", ["lock_expires_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_email_outbox_lock_expires_at", table_name="email_outbox")
    op.drop_index("ix_email_outbox_next_attempt_at", table_name="email_outbox")

    op.drop_column("email_outbox", "worker_metadata_json")
    op.drop_column("email_outbox", "dead_lettered_at")
    op.drop_column("email_outbox", "next_attempt_at")
    op.drop_column("email_outbox", "last_attempt_at")
    op.drop_column("email_outbox", "lock_expires_at")
    op.drop_column("email_outbox", "locked_by")
    op.drop_column("email_outbox", "locked_at")
