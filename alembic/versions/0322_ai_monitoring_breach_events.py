"""ai_monitoring_breach_events: per-tier compliance decision records (patent P4)

NEW table. Core has never had one -- verified absent from models, migrations, schemas
and both live databases before this was written. Today an AI-monitoring breach leaves
only `ai_monitoring_readings.within_threshold = false` plus a ControlMonitoringAlert
whose linkage back to the config is untyped JSON.

This table records, per breached tier, the decision core made and the workflow it
initiated. One row per (reading, tier) -- enforced by a unique index -- so the audit
trail answers "which tier fired?" rather than only "a breach happened".

Both operands of the comparison are frozen onto the row (observed_value,
threshold_value, threshold_operator) alongside the obligation the decision was made
under. A later edit to the config must not silently rewrite the history of decisions
already taken.

Numeric(10,4), not Float, and not by accident: this is an audit record of a comparison,
and it mirrors ai_monitoring_readings.value exactly. Storing the operands as binary
floats when the values they came from were decimals would let a stored decision
disagree with a recomputation of it at the fourth decimal place -- rare, unreproducible
and catastrophic to explain to a regulator.

id default: `gen_random_uuid()` on PostgreSQL (matching 0129's convention on the sibling
tables) so raw-SQL inserts work; the ORM model additionally supplies `default=uuid.uuid4`
via UUIDPrimaryKeyMixin, which is what covers SQLite in the test harness. Both paths are
therefore defaulted on every dialect this runs on.

`workflow_triggered` is deliberately NOT CHECK-constrained. It records what was actually
dispatched at the time, and an audit record must stay valid even if that workflow value
is later removed from the config vocabulary. `threshold_operator` IS constrained: it is
a stable comparison vocabulary, not a historical dispatch label.

Identifier lengths (63-byte limit): ai_monitoring_breach_events (27),
uq_ai_monitoring_breach_events_reading_tier (43),
ix_ai_monitoring_breach_events_org_system_decided (49),
ix_ai_monitoring_breach_events_obligation (41),
fk_ai_monitoring_breach_events_obligation (41),
ck_ai_monitoring_breach_events_operator (39). All FK/CHECK names are explicit rather
than generated, so none can silently exceed the limit.

Revision ID: 0322_ai_monitoring_breach_events
Revises: 0321_ai_monitoring_p4_reading_provenance
Create Date: 2026-07-21 00:00:00.000000
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

logger = logging.getLogger(__name__)

revision: str = "0322_ai_monitoring_breach_events"
down_revision: str | None = "0321_ai_monitoring_p4_reading_provenance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "ai_monitoring_breach_events"
UNIQUE_INDEX = "uq_ai_monitoring_breach_events_reading_tier"
LOOKUP_INDEX = "ix_ai_monitoring_breach_events_org_system_decided"
OBLIGATION_INDEX = "ix_ai_monitoring_breach_events_obligation"
OPERATOR_CHECK = "ck_ai_monitoring_breach_events_operator"

THRESHOLD_OPERATORS = ("gt", "lt", "gte", "lte")


def _inspector():
    return sa.inspect(op.get_bind())


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _uuid_pk_default():
    """`gen_random_uuid()` on PostgreSQL, nothing elsewhere.

    Matches 0129's server default on the sibling monitoring tables. On SQLite (test
    harness only) the ORM's UUIDPrimaryKeyMixin `default=uuid.uuid4` supplies the id.
    """
    return sa.text("gen_random_uuid()") if _is_postgres() else None


def upgrade() -> None:
    if TABLE in _inspector().get_table_names():
        raise RuntimeError(
            f"{TABLE} already exists. Core does not create this table -- it is "
            "introduced by P4 -- so its presence means a previous partial P4 "
            "deployment left it behind, not that there is a core schema to adapt to. "
            "Refusing to ALTER a table of unknown provenance. Remedy: confirm what "
            "created it, reconcile or drop it deliberately, then re-run."
        )

    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=_uuid_pk_default()),
        # Denormalised from the reading's own organization_id so that every tenancy
        # filter in core -- which is manual, per query, with no RLS -- can scope this
        # table without a join. A join that someone forgets is a cross-tenant leak.
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("reading_id", sa.Uuid(), nullable=False),
        sa.Column("config_id", sa.Uuid(), nullable=False),
        sa.Column("ai_system_id", sa.Uuid(), nullable=False),
        sa.Column("metric_type", sa.String(64), nullable=False),
        sa.Column("tier", sa.String(32), nullable=False, server_default="warning"),
        sa.Column("escalation_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("observed_value", sa.Numeric(10, 4), nullable=False),
        sa.Column("threshold_value", sa.Numeric(10, 4), nullable=False),
        sa.Column("threshold_operator", sa.String(8), nullable=False),
        # Frozen alongside the operands, and for the same reason: this is the duty the
        # decision was made under, even if the config is later relinked. Nullable
        # because a threshold may not have been obligation-linked when it fired.
        sa.Column("obligation_id", sa.Uuid(), nullable=True),
        sa.Column("workflow_triggered", sa.String(32), nullable=False),
        # Nullable: the workflow engine's reference is only known after dispatch
        # succeeds, and a dispatch failure must not lose the record that core decided
        # a breach occurred.
        sa.Column("workflow_reference", sa.String(128), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("decided_by", sa.String(64), nullable=False, server_default="core.compliance_event_bridge"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE",
            name="fk_ai_monitoring_breach_events_org",
        ),
        sa.ForeignKeyConstraint(
            ["reading_id"], ["ai_monitoring_readings.id"], ondelete="CASCADE",
            name="fk_ai_monitoring_breach_events_reading",
        ),
        # RESTRICT, not CASCADE: deleting a threshold config must not erase the record
        # of decisions already made under it. Those decisions happened, and a
        # compliance system does not get to forget them because someone tidied a config.
        sa.ForeignKeyConstraint(
            ["config_id"], ["ai_monitoring_configs.id"], ondelete="RESTRICT",
            name="fk_ai_monitoring_breach_events_config",
        ),
        sa.ForeignKeyConstraint(
            ["ai_system_id"], ["ai_systems.id"], ondelete="CASCADE",
            name="fk_ai_monitoring_breach_events_system",
        ),
        sa.ForeignKeyConstraint(
            ["obligation_id"], ["obligations.id"], ondelete="SET NULL",
            name="fk_ai_monitoring_breach_events_obligation",
        ),
    )

    # ONE ROW PER BREACHED TIER -- the constraint that makes the audit trail answer
    # "which tier?" rather than only "a breach happened".
    op.create_index(UNIQUE_INDEX, TABLE, ["reading_id", "tier"], unique=True)
    op.create_index(LOOKUP_INDEX, TABLE, ["organization_id", "ai_system_id", "decided_at"])
    op.create_index(OBLIGATION_INDEX, TABLE, ["obligation_id"])

    if _is_postgres():
        operators = ", ".join(f"'{v}'" for v in THRESHOLD_OPERATORS)
        op.create_check_constraint(OPERATOR_CHECK, TABLE, f"threshold_operator IN ({operators})")
    else:
        logger.info("skipping %s on %s (test dialect)", OPERATOR_CHECK, op.get_bind().dialect.name)


def downgrade() -> None:
    """Drop the table only when it is EMPTY.

    Breach events are compliance audit records. With rows present this refuses:
    destroying them must be a deliberate manual act, not a side-effect of rolling back
    a deployment.
    """
    rows = op.get_bind().execute(sa.text(f"SELECT COUNT(*) FROM {TABLE}")).scalar()
    if rows:
        raise RuntimeError(
            f"cannot downgrade: {TABLE} holds {rows} compliance decision record(s). "
            "These document breaches core determined and the governance workflows it "
            "initiated; a downgrade will not delete them. Remedy: export them for "
            "retention, drop the table deliberately, then re-run."
        )

    op.drop_index(OBLIGATION_INDEX, table_name=TABLE)
    op.drop_index(LOOKUP_INDEX, table_name=TABLE)
    op.drop_index(UNIQUE_INDEX, table_name=TABLE)
    op.drop_table(TABLE)
