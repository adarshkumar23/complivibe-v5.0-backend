"""add audit_findings.engagement_scope_snapshot for scope-drift detection

Revision ID: 0263_audit_finding_scope_snapshot
Revises: 0262_escalation_events_reason_column
Create Date: 2026-07-07 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0263_audit_finding_scope_snapshot"
down_revision: str | None = "0262_escalation_events_reason_column"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "audit_findings",
        sa.Column("engagement_scope_snapshot", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.alter_column("audit_findings", "engagement_scope_snapshot", server_default=None)


def downgrade() -> None:
    op.drop_column("audit_findings", "engagement_scope_snapshot")
