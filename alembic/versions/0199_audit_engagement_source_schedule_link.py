"""add audit_engagements.source_schedule_id for real schedule-history scoping

Revision ID: 0199_audit_engagement_source_schedule_link
Revises: 0198_add_risk_assessment_to_issue_source_type
Create Date: 2026-07-03 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0199_audit_engagement_source_schedule_link"
down_revision: str | None = "0198_add_risk_assessment_to_issue_source_type"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "audit_engagements",
        sa.Column("source_schedule_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_audit_engagements_source_schedule_id",
        "audit_engagements",
        "audit_schedules",
        ["source_schedule_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_audit_engagements_org_source_schedule",
        "audit_engagements",
        ["organization_id", "source_schedule_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_engagements_org_source_schedule", table_name="audit_engagements")
    op.drop_constraint("fk_audit_engagements_source_schedule_id", "audit_engagements", type_="foreignkey")
    op.drop_column("audit_engagements", "source_schedule_id")
