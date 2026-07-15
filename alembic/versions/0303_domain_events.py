"""add domain_events table (persisted event-bus history)

Revision ID: 0303_domain_events
Revises: 0302_raise_api_general_rate_limit_default
Create Date: 2026-07-14 12:00:00.000000

Interconnection Phase 1 -- Domain Event Bus. The in-process EventBus
(app/core/event_bus.py) now persists every published event to this append-only
table before dispatching to listeners. This is a durable audit trail of
cross-domain signal flow (which event fired, for which org/entity, in which
correlation cascade) -- it is NOT a replacement for AuditService.write_audit_log,
which independently records the resulting downstream state changes.

Rows are immutable (append-only): the application exposes no update/delete path,
consistent with the audit-log lifecycle pattern (ADR-004/ADR-008). organization_id
is strictly non-nullable for tenant scoping (ADR-002).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0303_domain_events"
down_revision: str | None = "0302_raise_api_general_rate_limit_default"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "domain_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("entity_type", sa.String(length=120), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column(
            "payload_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "previous_value",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column(
            "new_value",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("triggered_by", sa.String(length=64), nullable=False),
        sa.Column("triggered_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("correlation_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["triggered_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_domain_events_org_type_occurred",
        "domain_events",
        ["organization_id", "event_type", "occurred_at"],
    )
    op.create_index("ix_domain_events_correlation", "domain_events", ["correlation_id"])


def downgrade() -> None:
    op.drop_index("ix_domain_events_correlation", table_name="domain_events")
    op.drop_index("ix_domain_events_org_type_occurred", table_name="domain_events")
    op.drop_table("domain_events")
