"""task orchestration workflow

Revision ID: 0011_task_orchestration
Revises: 0010_risk_register_links
Create Date: 2026-06-18 14:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0011_task_orchestration"
down_revision: Union[str, Sequence[str], None] = "0010_risk_register_links"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("priority", sa.String(length=16), nullable=False, server_default="normal"))
    op.add_column("tasks", sa.Column("task_type", sa.String(length=32), nullable=False, server_default="general"))
    op.add_column("tasks", sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("tasks", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tasks", sa.Column("completed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("tasks", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tasks", sa.Column("cancelled_by_user_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("tasks", sa.Column("linked_entity_type", sa.String(length=64), nullable=True))
    op.add_column("tasks", sa.Column("linked_entity_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("tasks", sa.Column("source", sa.String(length=32), nullable=False, server_default="manual"))
    op.add_column("tasks", sa.Column("reminder_status", sa.String(length=32), nullable=False, server_default="none"))
    op.add_column("tasks", sa.Column("last_reminder_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tasks", sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    op.create_foreign_key(
        "fk_tasks_created_by_user_id_users",
        "tasks",
        "users",
        ["created_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_tasks_completed_by_user_id_users",
        "tasks",
        "users",
        ["completed_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_tasks_cancelled_by_user_id_users",
        "tasks",
        "users",
        ["cancelled_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_index("ix_task_org_priority", "tasks", ["organization_id", "priority"], unique=False)
    op.create_index("ix_tasks_owner_id", "tasks", ["owner_id"], unique=False)
    op.create_index("ix_tasks_due_at", "tasks", ["due_at"], unique=False)
    op.create_index(
        "ix_tasks_linked_entity",
        "tasks",
        ["organization_id", "linked_entity_type", "linked_entity_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_tasks_linked_entity", table_name="tasks")
    op.drop_index("ix_tasks_due_at", table_name="tasks")
    op.drop_index("ix_tasks_owner_id", table_name="tasks")
    op.drop_index("ix_task_org_priority", table_name="tasks")

    op.drop_constraint("fk_tasks_cancelled_by_user_id_users", "tasks", type_="foreignkey")
    op.drop_constraint("fk_tasks_completed_by_user_id_users", "tasks", type_="foreignkey")
    op.drop_constraint("fk_tasks_created_by_user_id_users", "tasks", type_="foreignkey")

    op.drop_column("tasks", "metadata_json")
    op.drop_column("tasks", "last_reminder_at")
    op.drop_column("tasks", "reminder_status")
    op.drop_column("tasks", "source")
    op.drop_column("tasks", "linked_entity_id")
    op.drop_column("tasks", "linked_entity_type")
    op.drop_column("tasks", "cancelled_by_user_id")
    op.drop_column("tasks", "cancelled_at")
    op.drop_column("tasks", "completed_by_user_id")
    op.drop_column("tasks", "completed_at")
    op.drop_column("tasks", "created_by_user_id")
    op.drop_column("tasks", "task_type")
    op.drop_column("tasks", "priority")
