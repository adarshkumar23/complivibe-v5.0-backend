"""ai_monitoring_configs: admit notify_oncall as a governance workflow (patent P4)

Widens ck_ai_monitoring_configs_workflow_to_trigger from the five values 0320 created
to six, adding `notify_oncall`. Separate from 0320 purely so the added value is a
reviewable one-line change with its own reversal, rather than being buried in the
column's introduction.

CHECK constraint, not a native ENUM -- so this is reversible without ALTER TYPE
gymnastics. (The upstream P4 revision of this migration used `ALTER TYPE ... ADD VALUE`
on a native enum and consequently had a no-op downgrade; that design was replaced.)

PostgreSQL only, for the same reason as 0320's metric_type widening: on SQLite the
constraint would have to be attached by rebuilding the table, and SQLite is only ever
the test harness here. Tests assert the column's behaviour; production gets the
constraint.

Revision ID: 0323_ai_monitoring_notify_oncall
Revises: 0322_ai_monitoring_breach_events
Create Date: 2026-07-21 00:00:00.000000
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

logger = logging.getLogger(__name__)

revision: str = "0323_ai_monitoring_notify_oncall"
down_revision: str | None = "0322_ai_monitoring_breach_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "ai_monitoring_configs"
CHECK_NAME = "ck_ai_monitoring_configs_workflow_to_trigger"
NEW_VALUE = "notify_oncall"

EXISTING_VALUES = (
    "create_alert",
    "create_issue",
    "update_risk_score",
    "require_review",
    "suspend_system",
)
ALL_VALUES = EXISTING_VALUES + (NEW_VALUE,)


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _set_allowed_values(values: tuple[str, ...]) -> None:
    if not _is_postgres():
        logger.info(
            "skipping %s on %s (test dialect); the constraint is PostgreSQL-only",
            CHECK_NAME,
            op.get_bind().dialect.name,
        )
        return
    rendered = ", ".join(f"'{v}'" for v in values)
    op.execute(sa.text(f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {CHECK_NAME}"))
    op.create_check_constraint(CHECK_NAME, TABLE, f"workflow_to_trigger IN ({rendered})")


def upgrade() -> None:
    _set_allowed_values(ALL_VALUES)


def downgrade() -> None:
    """Narrow the vocabulary back to five values.

    Refuses while any config still selects `notify_oncall`. Rewriting a live config's
    governance action to make a schema change fit would change what happens when that
    customer's threshold is next breached -- silently, and in the direction of doing
    less.
    """
    in_use = op.get_bind().execute(
        sa.text(f"SELECT COUNT(*) FROM {TABLE} WHERE workflow_to_trigger = :value"),
        {"value": NEW_VALUE},
    ).scalar()
    if in_use:
        raise RuntimeError(
            f"cannot downgrade: {in_use} config(s) use workflow_to_trigger='{NEW_VALUE}'. "
            "Repoint them at another workflow first -- this migration will not silently "
            "rewrite a governance action."
        )

    _set_allowed_values(EXISTING_VALUES)
