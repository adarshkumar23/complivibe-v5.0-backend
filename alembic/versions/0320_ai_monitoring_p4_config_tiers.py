"""ai_monitoring_configs: obligation linkage + severity tiers + workflow dispatch (patent P4)

Extends core's existing Feature #66 monitoring subsystem; it does NOT replace it.
`ai_monitoring_configs` is owned by 0129_ai_monitoring_mode_b and later altered by
0264_ai_monitoring_config_baseline_model_version. P4 adds a compliance-decision layer
on top of the engineer-chosen threshold that table already stores.

Current real shape of the table when this runs (transcribed from a live schema at
revision 0319, NOT from 0129 alone -- the upstream P4 snapshot was missing the 0264
column and would have described the table wrongly):

    id, organization_id, ai_system_id, metric_type, threshold_value,
    comparison_direction, alert_on_breach, check_frequency, baseline_value,
    last_checked_at, last_reading_value, api_key_hash, is_active, created_by,
    created_at, updated_at, deleted_at, baseline_model_version   <-- 0264

Columns added here
------------------
obligation_id        the regulatory duty the threshold derives from (stays NULLABLE:
                     an unlinked threshold is simply not obligation-derived, and
                     asserting provenance for hand-picked thresholds would be a lie)
tier                 severity label; several tiers may be active per metric
escalation_order     ordering/reporting only, never used to skip a tier
threshold_operator   gt/lt/gte/lte, strictly more expressive than comparison_direction
                     which is retained untouched
workflow_to_trigger  the governance workflow a breach initiates

Every column is added nullable, backfilled to record what core ALREADY does, then
constrained. Feature #66's live behaviour is unchanged.

Identifier lengths (Postgres 63-byte limit): uq_ai_monitoring_configs_active_tier (36),
ix_ai_monitoring_configs_obligation (35), fk_ai_monitoring_configs_obligation (35),
ck_ai_monitoring_configs_threshold_operator (43),
ck_ai_monitoring_configs_workflow_to_trigger (44). All well under.

Revision ID: 0320_ai_monitoring_p4_config_tiers
Revises: 0319_reports_share_permission
Create Date: 2026-07-21 00:00:00.000000
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

logger = logging.getLogger(__name__)

revision: str = "0320_ai_monitoring_p4_config_tiers"
down_revision: str | None = "0319_reports_share_permission"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "ai_monitoring_configs"
TIERED_UNIQUE_INDEX = "uq_ai_monitoring_configs_active_tier"
OBLIGATION_INDEX = "ix_ai_monitoring_configs_obligation"
METRIC_TYPE_CHECK = "ck_ai_monitoring_configs_metric_type"
OPERATOR_CHECK = "ck_ai_monitoring_configs_threshold_operator"
WORKFLOW_CHECK = "ck_ai_monitoring_configs_workflow_to_trigger"
OBLIGATION_FK = "fk_ai_monitoring_configs_obligation"

#: Tier assigned to rows that predate the tier concept. Deliberately not 'warning' --
#: nobody chose a severity for these, and calling them 'warning' would assert one.
BACKFILL_TIER = "default"

THRESHOLD_OPERATORS = ("gt", "lt", "gte", "lte")

#: Five here, not six. `notify_oncall` is added by 0323, which is the only reason
#: that migration exists. Keep the two in step.
WORKFLOW_VALUES = (
    "create_alert",
    "create_issue",
    "update_risk_score",
    "require_review",
    "suspend_system",
)

#: Core's six metric types, plus P4's sixteen. Union, not replacement -- removing any
#: of core's six would break Feature #66's live configs. `output_drift`/`drift` and
#: `bias_parity_gap`/`bias` are near-synonyms kept separate on purpose: core's are
#: user-configured labels, P4's name a specific computation. Merging them would
#: silently change what an existing Feature #66 threshold means.
CORE_METRIC_TYPES = (
    "accuracy",
    "bias_parity_gap",
    "output_drift",
    "confidence_distribution",
    "response_time",
    "error_rate",
)
P4_METRIC_TYPES = (
    "drift",
    "data_quality",
    "bias",
    "estimated_accuracy",
    "hallucination_rate",
    "rag_faithfulness",
    "rag_answer_relevancy",
    "token_cost",
    "latency_p95",
    "refusal_rate",
    "drift_seasonal",
    "bias_seasonal",
    "estimated_accuracy_seasonal",
    "prompt_injection_rate",
    "rag_context_precision",
    "rag_context_recall",
)
ALL_METRIC_TYPES = CORE_METRIC_TYPES + P4_METRIC_TYPES

#: Faithful translation of core's own comparison. From AIMonitoringService.check_threshold:
#:     if comparison_direction == "above": return value >= threshold_value
#:     return value <= threshold_value
#: so 'above' is exactly `gte` and 'below' is exactly `lte`. This mapping changes no
#: existing threshold's meaning, not even at a boundary.
DIRECTION_TO_OPERATOR = {"above": "gte", "below": "lte"}


def _inspector():
    return sa.inspect(op.get_bind())


def _column_names() -> set[str]:
    return {c["name"] for c in _inspector().get_columns(TABLE)}


def _index_names() -> set[str]:
    return {i["name"] for i in _inspector().get_indexes(TABLE)}


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _require_table() -> None:
    """The table must already exist -- 0129 created it, 0264 altered it."""
    if TABLE not in _inspector().get_table_names():
        raise RuntimeError(
            f"{TABLE} does not exist. It is created by core's migration "
            "0129_ai_monitoring_mode_b, an ancestor of this revision. Its absence "
            "means the migration chain is broken or this is not a complivibe "
            "database. Refusing to create the table: P4 extends core's monitoring "
            "schema and must not fork it."
        )


def upgrade() -> None:
    _require_table()

    # Checked FIRST, before any DDL. PostgreSQL has transactional DDL and Alembic wraps
    # each revision in a transaction, so raising later would roll back every column this
    # migration had added -- meaning a remedy phrased as "edit the new columns in place"
    # would be impossible to follow. Fail before doing any work, and give a remedy that
    # only uses columns which exist at that point.
    _assert_no_tier_collisions()

    columns = _column_names()

    # 1. Add every new column as NULLABLE. No server_default at this stage: a default
    #    would mask whether the backfill actually ran, and "did the backfill run?" is
    #    the only question that matters if this is ever interrupted.
    if "obligation_id" not in columns:
        op.add_column(TABLE, sa.Column("obligation_id", sa.Uuid(), nullable=True))
    if "tier" not in columns:
        op.add_column(TABLE, sa.Column("tier", sa.String(32), nullable=True))
    if "escalation_order" not in columns:
        op.add_column(TABLE, sa.Column("escalation_order", sa.Integer(), nullable=True))
    if "threshold_operator" not in columns:
        op.add_column(TABLE, sa.Column("threshold_operator", sa.String(8), nullable=True))
    if "workflow_to_trigger" not in columns:
        op.add_column(TABLE, sa.Column("workflow_to_trigger", sa.String(32), nullable=True))

    _backfill()

    # 2. NOT NULL, only after the backfill. obligation_id stays nullable on purpose --
    #    see the module docstring.
    with op.batch_alter_table(TABLE) as batch:
        batch.alter_column("tier", existing_type=sa.String(32), nullable=False, server_default=BACKFILL_TIER)
        batch.alter_column("escalation_order", existing_type=sa.Integer(), nullable=False, server_default="0")
        batch.alter_column("threshold_operator", existing_type=sa.String(8), nullable=False)
        batch.alter_column(
            "workflow_to_trigger", existing_type=sa.String(32), nullable=False, server_default="create_alert"
        )

    _widen_metric_type_check()
    _add_value_checks()
    _add_obligation_fk()

    if OBLIGATION_INDEX not in _index_names():
        op.create_index(OBLIGATION_INDEX, TABLE, ["obligation_id"])

    _create_tiered_unique_index()


def _backfill() -> None:
    """Record what core already does. Invent nothing.

    Each statement is guarded on IS NULL so a re-run after a partial failure resumes
    rather than overwriting rows written by hand in the interim.
    """
    configs = sa.table(
        TABLE,
        sa.column("tier", sa.String),
        sa.column("escalation_order", sa.Integer),
        sa.column("threshold_operator", sa.String),
        sa.column("workflow_to_trigger", sa.String),
        sa.column("comparison_direction", sa.String),
    )

    op.execute(configs.update().where(configs.c.tier.is_(None)).values(tier=BACKFILL_TIER))
    op.execute(configs.update().where(configs.c.escalation_order.is_(None)).values(escalation_order=0))

    for direction, operator in DIRECTION_TO_OPERATOR.items():
        op.execute(
            configs.update()
            .where(
                sa.and_(
                    configs.c.threshold_operator.is_(None),
                    configs.c.comparison_direction == direction,
                )
            )
            .values(threshold_operator=operator)
        )

    # A row whose comparison_direction is somehow neither 'above' nor 'below' would
    # survive the loop with a NULL operator and then fail the NOT NULL below with an
    # opaque error. Core has a CHECK that should make this impossible; "should be
    # impossible" is not a reason to fail obscurely.
    orphans = op.get_bind().execute(
        sa.text(f"SELECT COUNT(*) FROM {TABLE} WHERE threshold_operator IS NULL")
    ).scalar()
    if orphans:
        raise RuntimeError(
            f"{orphans} row(s) in {TABLE} have a comparison_direction that is neither "
            "'above' nor 'below', so threshold_operator cannot be derived. Inspect "
            f"with: SELECT id, comparison_direction FROM {TABLE} WHERE "
            "threshold_operator IS NULL; correct them, then re-run. This migration "
            "will not guess which way a compliance threshold compares."
        )

    # 'create_alert' is what core does today -- _create_breach_alert() builds a
    # ControlMonitoringAlert on every breach where alert_on_breach is true. This
    # describes existing behaviour rather than changing it; alert_on_breach is left
    # untouched and still gates dispatch for these rows.
    op.execute(
        configs.update()
        .where(configs.c.workflow_to_trigger.is_(None))
        .values(workflow_to_trigger="create_alert")
    )


def _widen_metric_type_check() -> None:
    """Admit P4's metric vocabulary alongside core's.

    Core's CHECK allows six values; none of P4's is among them, so without this every
    P4 config insert fails.

    PostgreSQL only: on SQLite the constraint is inline in the CREATE TABLE and cannot
    be altered without rebuilding the table, and SQLite is only ever the test harness.
    """
    if not _is_postgres():
        logger.info(
            "skipping %s widening on %s (test dialect); the constraint is PostgreSQL-only",
            METRIC_TYPE_CHECK,
            op.get_bind().dialect.name,
        )
        return

    values = ", ".join(f"'{v}'" for v in ALL_METRIC_TYPES)
    # IF EXISTS matches core's own convention (see 0316/0317) and turns a re-run after
    # a partial failure into a no-op instead of an error.
    op.execute(sa.text(f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {METRIC_TYPE_CHECK}"))
    op.create_check_constraint(METRIC_TYPE_CHECK, TABLE, f"metric_type IN ({values})")


def _add_value_checks() -> None:
    """CHECK constraints for the two new closed vocabularies.

    String + CHECK, never sa.Enum: every constraint 0129 put on this table is a CHECK,
    and native ENUM is disallowed by this codebase's standing schema rules.
    """
    if not _is_postgres():
        logger.info("skipping CHECK constraints on %s (test dialect)", op.get_bind().dialect.name)
        return

    operators = ", ".join(f"'{v}'" for v in THRESHOLD_OPERATORS)
    op.execute(sa.text(f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {OPERATOR_CHECK}"))
    op.create_check_constraint(OPERATOR_CHECK, TABLE, f"threshold_operator IN ({operators})")

    workflows = ", ".join(f"'{v}'" for v in WORKFLOW_VALUES)
    op.execute(sa.text(f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {WORKFLOW_CHECK}"))
    op.create_check_constraint(WORKFLOW_CHECK, TABLE, f"workflow_to_trigger IN ({workflows})")


def _add_obligation_fk() -> None:
    """FK to core's global obligation catalog.

    `obligations` is NOT organization-owned -- it is shared framework content -- so
    this FK crosses from a tenant-scoped row to a global one. That direction is safe:
    the catalog is identical for everyone, so it cannot leak between tenants. The
    config's own organization_id remains the only tenancy control on the row.

    SET NULL rather than CASCADE or RESTRICT, matching core's own controls.obligation_id.
    Retiring an obligation must not delete a customer's threshold, nor be blocked by it.
    """
    if not _is_postgres():
        logger.info("skipping obligation FK on %s (test dialect)", op.get_bind().dialect.name)
        return
    op.execute(sa.text(f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {OBLIGATION_FK}"))
    op.create_foreign_key(
        OBLIGATION_FK, TABLE, "obligations", ["obligation_id"], ["id"], ondelete="SET NULL"
    )


def _assert_no_tier_collisions() -> None:
    """Refuse rather than fail obscurely on the unique index.

    Core never constrained (ai_system_id, metric_type): its indexes are non-unique.
    Nothing stopped an org from creating two active configs for one metric -- and the
    product invites it, since two thresholds on one metric is how a user approximates
    severity tiers today. The backfill would collapse every such row onto
    tier='default', making those pairs duplicates under the new unique index.

    Runs BEFORE any DDL, and the remedy below deliberately references only columns that
    exist at that moment. `tier` does not yet exist when this fires, so a remedy telling
    an operator to "assign distinct tiers" would be unfollowable -- and because Postgres
    DDL is transactional, nothing this migration did survives the raise either.

    Nothing is deleted: these are live compliance thresholds, and choosing which one
    survives is not a decision a migration gets to make.
    """
    duplicates = op.get_bind().execute(
        sa.text(
            f"SELECT COUNT(*) FROM (SELECT ai_system_id, metric_type FROM {TABLE} "
            "WHERE is_active GROUP BY ai_system_id, metric_type HAVING COUNT(*) > 1) AS d"
        )
    ).scalar()
    if not duplicates:
        return
    raise RuntimeError(
        f"cannot create {TIERED_UNIQUE_INDEX}: {duplicates} (ai_system_id, metric_type) "
        "group(s) have more than one ACTIVE config. Core never enforced uniqueness "
        f"here, and this migration would put them all on tier='{BACKFILL_TIER}', which "
        "the new unique index forbids.\n"
        "Inspect them with:\n"
        f"  SELECT ai_system_id, metric_type, COUNT(*), array_agg(id) FROM {TABLE}\n"
        "   WHERE is_active GROUP BY ai_system_id, metric_type HAVING COUNT(*) > 1;\n"
        "Remedy: deactivate all but one config in each group\n"
        f"  UPDATE {TABLE} SET is_active = false WHERE id IN (...);\n"
        "then re-run. The unique index is partial on is_active, so deactivated configs "
        "are retained and remain queryable for audit. After the migration you can "
        "re-activate them with distinct tier values (e.g. 'warning' and 'critical', "
        "escalation_order 0 and 1), which is the supported way to express what those "
        "duplicate configs were approximating. No threshold is deleted by this "
        "migration or by that remedy."
    )


def _create_tiered_unique_index() -> None:
    """One ACTIVE config per (system, metric, tier).

    Several tiers may be active on one metric -- that is the point. A duplicate tier on
    one metric is still ambiguous and stays blocked. Partial on is_active so superseded
    configs are retained for audit.
    """
    if TIERED_UNIQUE_INDEX in _index_names():
        return
    op.create_index(
        TIERED_UNIQUE_INDEX,
        TABLE,
        ["ai_system_id", "metric_type", "tier"],
        unique=True,
        postgresql_where=sa.text("is_active"),
        sqlite_where=sa.text("is_active"),
    )


def downgrade() -> None:
    """Remove P4's columns, leaving the 0129+0264 table exactly as it was.

    LOSSY, and deliberately so in one direction only: it refuses when the loss would be
    a compliance decision rather than a schema detail. Dropping `tier` from a metric
    with several active tiers would silently discard every threshold but one, and which
    one survives is a judgement about regulatory exposure.

    obligation_id links are lost with no equivalent guard, because the column is removed
    wholesale rather than collapsed -- no ambiguity to resolve, only data to restore
    from backup. The asymmetry is intentional but worth knowing before running this.
    """
    duplicates = op.get_bind().execute(
        sa.text(
            f"SELECT COUNT(*) FROM (SELECT ai_system_id, metric_type FROM {TABLE} "
            "WHERE is_active GROUP BY ai_system_id, metric_type HAVING COUNT(*) > 1) AS d"
        )
    ).scalar()
    if duplicates:
        raise RuntimeError(
            f"cannot downgrade: {duplicates} (ai_system_id, metric_type) pair(s) have "
            "multiple active tiers. Decide which tier survives and deactivate the "
            "others first -- this migration will not silently delete compliance "
            "thresholds."
        )

    if TIERED_UNIQUE_INDEX in _index_names():
        op.drop_index(TIERED_UNIQUE_INDEX, table_name=TABLE)
    if OBLIGATION_INDEX in _index_names():
        op.drop_index(OBLIGATION_INDEX, table_name=TABLE)

    if _is_postgres():
        op.execute(sa.text(f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {OBLIGATION_FK}"))
        for name in (OPERATOR_CHECK, WORKFLOW_CHECK):
            op.execute(sa.text(f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {name}"))

        # Narrowing the CHECK back to core's six fails if any config uses a P4 metric
        # type. Name that here rather than letting Postgres raise a bare check_violation.
        p4_values = ", ".join(f"'{v}'" for v in P4_METRIC_TYPES)
        stragglers = op.get_bind().execute(
            sa.text(f"SELECT COUNT(*) FROM {TABLE} WHERE metric_type IN ({p4_values})")
        ).scalar()
        if stragglers:
            raise RuntimeError(
                f"cannot downgrade: {stragglers} config(s) use a P4 metric type that "
                "core's original CHECK does not allow. Remedy: repoint or deactivate "
                f"them (SELECT id, metric_type FROM {TABLE} WHERE metric_type IN "
                f"({p4_values})), then re-run. Deleting them here would destroy live "
                "compliance thresholds."
            )
        values = ", ".join(f"'{v}'" for v in CORE_METRIC_TYPES)
        op.execute(sa.text(f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {METRIC_TYPE_CHECK}"))
        op.create_check_constraint(METRIC_TYPE_CHECK, TABLE, f"metric_type IN ({values})")

    with op.batch_alter_table(TABLE) as batch:
        batch.drop_column("workflow_to_trigger")
        batch.drop_column("threshold_operator")
        batch.drop_column("escalation_order")
        batch.drop_column("tier")
        batch.drop_column("obligation_id")
