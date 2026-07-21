"""ai_monitoring_readings: collection provenance + tiered-verdict nullability (patent P4)

Extends core's 0129 readings table so a measurement can record HOW it was collected and
WHAT was measured, and so a reading can exist without a single-config boolean verdict.

Current real shape when this runs (transcribed from a live schema at revision 0319):

    id, organization_id, config_id, value, reading_source, source_tool,
    within_threshold, created_at

Columns added
-------------
collection_mode  'a' (in-environment agent) | 'b' (external push) | 'c' (scheduled pull)
metric_type      what was measured, when the reading is not tied to one config
sample_size      how many observations the value summarises
computed_by      which implementation produced it (e.g. 'evidently', 'builtin-psi')
reported_at      when the measurement happened, as distinct from when core received it

Two relaxations, and what they mean
-----------------------------------
1. `config_id` becomes NULLABLE. A metric can be collected for a system before anyone
   has configured a threshold for it. Under NOT NULL those measurements have nowhere
   to go and would be dropped. A measurement is a fact; it survives whether or not a
   threshold governs it yet.

2. `within_threshold` becomes NULLABLE, meaning "no single-config verdict". With tiered
   thresholds one reading has as many verdicts as the metric has tiers, and those live
   in ai_monitoring_breach_events with their tier attached. One boolean cannot answer
   the question any more.

CAUTION -- these relaxations are NOT semantically free. The upstream P4 migration
claimed "neither relaxation changes an existing query's result". That is FALSE and was
verified false against this codebase: `ai_governance_dashboard_service` uses
`.is_(False)` (NULL-safe), but `ai_recommendation_engine` and `ai_monitoring_service`
used Python truthiness (`not r.within_threshold`), where `not None` is True -- turning
every unjudged reading into a phantom breach. `MonitoringReadingRead` also declared both
columns non-optional, which would 500 on serialisation. Those three defects are fixed in
the same batch as this migration; do not run this migration without those fixes present.

NO server_default on reported_at: `ADD COLUMN ... DEFAULT CURRENT_TIMESTAMP` is accepted
by PostgreSQL but rejected by SQLite ("Cannot add a column with non-constant default").

Identifier lengths: ix_ai_monitoring_readings_mode_reported (39). Under the 63-byte limit.

Revision ID: 0321_ai_monitoring_p4_reading_provenance
Revises: 0320_ai_monitoring_p4_config_tiers
Create Date: 2026-07-21 00:00:00.000000
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

logger = logging.getLogger(__name__)

revision: str = "0321_ai_monitoring_p4_reading_provenance"
down_revision: str | None = "0320_ai_monitoring_p4_config_tiers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "ai_monitoring_readings"
LOOKUP_INDEX = "ix_ai_monitoring_readings_mode_reported"
COLLECTION_MODE_CHECK = "ck_ai_monitoring_readings_collection_mode"

COLLECTION_MODES = ("a", "b", "c")

#: Collection mode assigned to readings that predate the mode concept. 'b' because
#: external-tool push is the only ingest path that existed before this work -- core's
#: reading_source vocabulary is exactly {'manual', 'api_report'}, both of which are
#: Mode B or hand entry. Confirmed against core's real CHECK constraint.
BACKFILL_COLLECTION_MODE = "b"

#: A column matching any of these means the measurement table is storing a judgement.
#: Substring match, so `is_breach`, `breach_flag` and `breached_at` are all caught.
VERDICT_COLUMN_FRAGMENTS = (
    "breach",
    "severity",
    "violation",
    "alert_level",
    "verdict",
    "decision",
    "compliance_status",
    "threshold_exceeded",
    "risk_level",
)

#: `within_threshold` is core's OWN computed field, not a received verdict -- core
#: calculates it in AIMonitoringService.check_threshold from its own stored config.
#: This exemption is narrow and named on purpose: one known-good column, not a pattern.
VERDICT_EXEMPT_COLUMNS = ("within_threshold",)


def _inspector():
    return sa.inspect(op.get_bind())


def _column_names() -> set[str]:
    return {c["name"] for c in _inspector().get_columns(TABLE)}


def _index_names() -> set[str]:
    return {i["name"] for i in _inspector().get_indexes(TABLE)}


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _require_table() -> None:
    if TABLE not in _inspector().get_table_names():
        raise RuntimeError(
            f"{TABLE} does not exist. It is created by core's migration "
            "0129_ai_monitoring_mode_b, an ancestor of this revision. Its absence "
            "means the migration chain is broken. Refusing to create it: P4 extends "
            "core's readings table and must not fork it."
        )


def _assert_no_verdict_columns() -> None:
    """Refuse if a verdict arrived with the data instead of being computed.

    A column here named `is_breach` or `severity` would mean something outside core had
    told core what a reading meant. Known to pass against core's real schema today; kept
    because it costs one query and guards the invariant against a column added later,
    which is exactly when nobody would be looking for it.

    It raises rather than dropping: those values would be evidence about how the live
    system had been behaving, and must be exported and analysed before destruction.
    """
    offenders = sorted(
        name
        for name in _column_names()
        if name not in VERDICT_EXEMPT_COLUMNS
        and any(fragment in name.lower() for fragment in VERDICT_COLUMN_FRAGMENTS)
    )
    if not offenders:
        return
    raise RuntimeError(
        f"{TABLE} carries verdict-shaped column(s): {', '.join(offenders)}. A readings "
        "table records what was measured, not what it meant. Do NOT simply drop these "
        "-- they are evidence of how the system has been behaving. Remedy, in order: "
        "(1) export the values with their reading ids, (2) determine whether any "
        "external caller has been supplying them, (3) migrate anything attributable "
        "into ai_monitoring_breach_events as core-authored decisions, (4) drop the "
        "columns in a reviewed migration, (5) re-run this one."
    )


def upgrade() -> None:
    _require_table()
    _assert_no_verdict_columns()

    columns = _column_names()

    if "collection_mode" not in columns:
        op.add_column(TABLE, sa.Column("collection_mode", sa.String(1), nullable=True))
    if "metric_type" not in columns:
        op.add_column(TABLE, sa.Column("metric_type", sa.String(64), nullable=True))
    if "sample_size" not in columns:
        op.add_column(TABLE, sa.Column("sample_size", sa.Integer(), nullable=True))
    if "computed_by" not in columns:
        op.add_column(TABLE, sa.Column("computed_by", sa.String(64), nullable=True))
    if "reported_at" not in columns:
        op.add_column(TABLE, sa.Column("reported_at", sa.DateTime(timezone=True), nullable=True))

    readings = sa.table(TABLE, sa.column("collection_mode", sa.String))
    op.execute(
        readings.update()
        .where(readings.c.collection_mode.is_(None))
        .values(collection_mode=BACKFILL_COLLECTION_MODE)
    )

    # collection_mode becomes NOT NULL: every reading arrived somehow, and 'unknown' is
    # not a useful state to permit.
    #
    # reported_at stays NULLABLE, deliberately. Historical rows have no knowable
    # measurement time; copying created_at into it would fabricate audit data by
    # asserting the measurement happened exactly when core received it.
    with op.batch_alter_table(TABLE) as batch:
        batch.alter_column(
            "collection_mode",
            existing_type=sa.String(1),
            nullable=False,
            server_default=BACKFILL_COLLECTION_MODE,
        )
        # The two relaxations. See the module docstring for what they cost.
        batch.alter_column("config_id", existing_type=sa.Uuid(), nullable=True)
        batch.alter_column("within_threshold", existing_type=sa.Boolean(), nullable=True)

    # The upstream migration defined a COLLECTION_MODES tuple and never used it, leaving
    # a NOT NULL String(1) with no value enforcement while every other closed vocabulary
    # on these tables is CHECK-constrained. Constrain it, consistently.
    if _is_postgres():
        modes = ", ".join(f"'{v}'" for v in COLLECTION_MODES)
        op.execute(sa.text(f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {COLLECTION_MODE_CHECK}"))
        op.create_check_constraint(COLLECTION_MODE_CHECK, TABLE, f"collection_mode IN ({modes})")
    else:
        logger.info("skipping %s on %s (test dialect)", COLLECTION_MODE_CHECK, op.get_bind().dialect.name)

    if LOOKUP_INDEX not in _index_names():
        op.create_index(LOOKUP_INDEX, TABLE, ["organization_id", "collection_mode", "reported_at"])


def downgrade() -> None:
    """Restore 0129's shape.

    Refuses while any row would violate a restored NOT NULL, rather than inventing a
    value to make the constraint pass. A reading with no config is a measurement core
    was asked to keep; assigning it to some config in order to downgrade is fabrication.
    """
    bind = op.get_bind()

    orphans = bind.execute(sa.text(f"SELECT COUNT(*) FROM {TABLE} WHERE config_id IS NULL")).scalar()
    if orphans:
        raise RuntimeError(
            f"cannot downgrade: {orphans} reading(s) have no config_id, which core's "
            "original schema requires NOT NULL. These are measurements collected before "
            "a threshold was configured. Remedy: attach them to a config, or export and "
            "delete them deliberately, then re-run. This migration will not invent a "
            "config_id."
        )

    unjudged = bind.execute(
        sa.text(f"SELECT COUNT(*) FROM {TABLE} WHERE within_threshold IS NULL")
    ).scalar()
    if unjudged:
        raise RuntimeError(
            f"cannot downgrade: {unjudged} reading(s) have a NULL within_threshold -- "
            "tiered readings whose per-tier verdicts live in ai_monitoring_breach_events. "
            "Collapsing several tier verdicts into one boolean would assert something "
            "nobody decided. Remedy: export these rows together with their breach "
            "events, delete them deliberately, then re-run."
        )

    if _is_postgres():
        op.execute(sa.text(f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {COLLECTION_MODE_CHECK}"))

    if LOOKUP_INDEX in _index_names():
        op.drop_index(LOOKUP_INDEX, table_name=TABLE)

    with op.batch_alter_table(TABLE) as batch:
        batch.alter_column("within_threshold", existing_type=sa.Boolean(), nullable=False)
        batch.alter_column("config_id", existing_type=sa.Uuid(), nullable=False)
        batch.drop_column("reported_at")
        batch.drop_column("computed_by")
        batch.drop_column("sample_size")
        batch.drop_column("metric_type")
        batch.drop_column("collection_mode")
