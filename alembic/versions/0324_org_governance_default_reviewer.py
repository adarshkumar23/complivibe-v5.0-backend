"""organization_governance_settings: default_reviewer_user_id (patent P4)

Implements P4's `require_review` decision (DECISIONS_NEEDED.md #2, Option 2): a per-org
configurable default reviewer, so a system-initiated review has a real assignee without
inventing one.

DELIBERATELY NOT a new table. The upstream P4 patch created `org_ai_governance_settings`
-- a fresh per-org singleton with one nullable user FK. Core already has
`organization_governance_settings`: the same shape (org-unique index, TimestampMixin, an
`updated_by_user_id` FK to users), already carrying per-org governance policy including
the Autopilot auto-execute settings and kill-switch. Adding a fourth near-identically
named per-org settings singleton alongside it, `org_ai_config` and
`organization_governance_setting_history` would be a maintenance trap: two tables whose
names differ by one word, both holding per-org AI-governance policy, with no rule for
which one a new setting belongs in.

So this is one nullable column on the table that already exists.

ondelete="SET NULL" matches the sibling `updated_by_user_id` column: deleting a user
must neither delete an organisation's governance settings nor be blocked by them. An
org whose default reviewer has left simply has no default reviewer again, which is the
same state as never having configured one -- and the workflow engine already has to
handle that state, so nothing new can break.

Identifier length: fk_org_governance_settings_default_reviewer (43), under the 63-byte
limit. Named explicitly rather than generated -- the generated name
(organization_governance_settings_default_reviewer_user_id_fkey) would be 61 bytes,
legal but uncomfortably close and easily pushed over by any later rename.

Revision ID: 0324_org_governance_default_reviewer
Revises: 0323_ai_monitoring_notify_oncall
Create Date: 2026-07-21 00:00:00.000000
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

logger = logging.getLogger(__name__)

revision: str = "0324_org_governance_default_reviewer"
down_revision: str | None = "0323_ai_monitoring_notify_oncall"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "organization_governance_settings"
COLUMN = "default_reviewer_user_id"
FK_NAME = "fk_org_governance_settings_default_reviewer"


def _inspector():
    return sa.inspect(op.get_bind())


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _column_names() -> set[str]:
    return {c["name"] for c in _inspector().get_columns(TABLE)}


def upgrade() -> None:
    if TABLE not in _inspector().get_table_names():
        raise RuntimeError(
            f"{TABLE} does not exist. It is core-owned and an ancestor of this "
            "revision creates it; its absence means the migration chain is broken."
        )

    if COLUMN in _column_names():
        logger.info("%s.%s already present; nothing to do", TABLE, COLUMN)
        return

    op.add_column(TABLE, sa.Column(COLUMN, sa.Uuid(), nullable=True))

    if _is_postgres():
        op.execute(sa.text(f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {FK_NAME}"))
        op.create_foreign_key(FK_NAME, TABLE, "users", [COLUMN], ["id"], ondelete="SET NULL")
    else:
        logger.info("skipping %s FK on %s (test dialect)", FK_NAME, op.get_bind().dialect.name)


def downgrade() -> None:
    """Drop the column.

    No data-loss guard: this is one freely reconfigurable configuration value per org,
    not audit history. Losing it means each org's default reviewer needs setting again,
    and until it is, system-initiated reviews fall back to the same unassigned path they
    take for an org that never configured one.
    """
    if COLUMN not in _column_names():
        return

    if _is_postgres():
        op.execute(sa.text(f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {FK_NAME}"))

    with op.batch_alter_table(TABLE) as batch:
        batch.drop_column(COLUMN)
