"""evolve audit schedules for auto-engagement creation

Revision ID: 0189_audit_scheduling_evidence_package_builder
Revises: 0188_pbc_requests_audit_findings_refresh
Create Date: 2026-07-01 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0189_audit_scheduling_evidence_package_builder"
down_revision: str | None = "0188_pbc_requests_audit_findings_refresh"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("audit_schedules", "audit_type", existing_type=sa.String(length=50), nullable=True)
    op.alter_column("audit_schedules", "framework_id", existing_type=postgresql.UUID(as_uuid=True), nullable=True)

    op.add_column(
        "audit_schedules",
        sa.Column("recurrence", sa.String(length=20), nullable=False, server_default=sa.text("'annual'")),
    )
    op.add_column(
        "audit_schedules",
        sa.Column("lead_time_days", sa.Integer(), nullable=False, server_default=sa.text("30")),
    )
    op.add_column(
        "audit_schedules",
        sa.Column("assigned_lead_auditor_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "audit_schedules",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "audit_schedules",
        sa.Column("last_triggered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "audit_schedules",
        sa.Column("next_due_date", sa.Date(), nullable=True),
    )

    op.execute("UPDATE audit_schedules SET recurrence = recurrence_pattern WHERE recurrence_pattern IS NOT NULL")
    op.execute("UPDATE audit_schedules SET next_due_date = next_audit_date WHERE next_audit_date IS NOT NULL")
    op.execute("UPDATE audit_schedules SET is_active = CASE WHEN status = 'active' THEN true ELSE false END")
    op.execute("UPDATE audit_schedules SET lead_time_days = preparation_reminder_days WHERE preparation_reminder_days IS NOT NULL")

    op.create_foreign_key(
        "fk_audit_sched_lead_aud",
        "audit_schedules",
        "users",
        ["assigned_lead_auditor_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_audit_sched_recur",
        "audit_schedules",
        "recurrence IN ('monthly', 'quarterly', 'semi_annual', 'annual')",
    )
    op.create_index("ix_audit_sched_org_active", "audit_schedules", ["organization_id", "is_active"], unique=False)
    op.create_index("ix_audit_sched_org_next_due", "audit_schedules", ["organization_id", "next_due_date"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_audit_sched_org_next_due", table_name="audit_schedules")
    op.drop_index("ix_audit_sched_org_active", table_name="audit_schedules")
    op.drop_constraint("ck_audit_sched_recur", "audit_schedules", type_="check")
    op.drop_constraint("fk_audit_sched_lead_aud", "audit_schedules", type_="foreignkey")

    op.drop_column("audit_schedules", "next_due_date")
    op.drop_column("audit_schedules", "last_triggered_at")
    op.drop_column("audit_schedules", "is_active")
    op.drop_column("audit_schedules", "assigned_lead_auditor_id")
    op.drop_column("audit_schedules", "lead_time_days")
    op.drop_column("audit_schedules", "recurrence")

    op.alter_column("audit_schedules", "framework_id", existing_type=postgresql.UUID(as_uuid=True), nullable=False)
    op.alter_column("audit_schedules", "audit_type", existing_type=sa.String(length=50), nullable=False)
