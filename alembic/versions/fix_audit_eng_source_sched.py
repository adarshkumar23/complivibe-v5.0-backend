"""add missing source_schedule_id to audit engagements

Revision ID: fix_audit_eng_source_sched
Revises: 0245_saml_replay
Create Date: 2026-07-06 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "fix_audit_eng_source_sched"
down_revision: str | None = "0245_saml_replay"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("audit_engagements")}
    fk_names = {fk["name"] for fk in inspector.get_foreign_keys("audit_engagements")}

    if "source_schedule_id" not in columns:
        op.add_column("audit_engagements", sa.Column("source_schedule_id", sa.Uuid(), nullable=True))

    if "fk_audit_engagements_source_schedule_id" not in fk_names:
        op.create_foreign_key(
            "fk_audit_engagements_source_schedule_id",
            "audit_engagements",
            "audit_schedules",
            ["source_schedule_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("audit_engagements")}
    fk_names = {fk["name"] for fk in inspector.get_foreign_keys("audit_engagements")}

    if "fk_audit_engagements_source_schedule_id" in fk_names:
        op.drop_constraint("fk_audit_engagements_source_schedule_id", "audit_engagements", type_="foreignkey")

    if "source_schedule_id" in columns:
        op.drop_column("audit_engagements", "source_schedule_id")
