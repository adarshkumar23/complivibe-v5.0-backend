"""rca and issue sla tracking

Revision ID: 0112_rca_and_issue_sla_tracking
Revises: 0111_formal_issue_log
Create Date: 2026-06-25 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0112_rca_and_issue_sla_tracking"
down_revision: str | None = "0111_formal_issue_log"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


DEFAULT_SLA_POLICIES: tuple[tuple[str, int, int], ...] = (
    ("critical", 1, 24),
    ("high", 4, 72),
    ("medium", 24, 168),
    ("low", 72, 720),
)


def upgrade() -> None:
    op.create_table(
        "root_cause_analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("issue_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("timeline_description", sa.Text(), nullable=False),
        sa.Column("root_cause", sa.Text(), nullable=False),
        sa.Column("contributing_factors", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("corrective_actions", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("preventive_measures", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("authored_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["issue_id"], ["issues.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["authored_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("issue_id", name="uq_root_cause_analyses_issue_id"),
    )
    op.create_index("ix_root_cause_analyses_org_issue", "root_cause_analyses", ["organization_id", "issue_id"], unique=False)
    op.create_index("ix_root_cause_analyses_org_authored", "root_cause_analyses", ["organization_id", "authored_by"], unique=False)

    op.create_table(
        "issue_sla_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("response_sla_hours", sa.Integer(), nullable=False),
        sa.Column("resolution_sla_hours", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("severity IN ('critical', 'high', 'medium', 'low')", name="ck_issue_sla_policies_severity"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "severity", name="uq_issue_sla_policies_org_severity"),
    )

    # Seed default severity SLA policies for all currently existing organizations.
    values_sql = " UNION ALL ".join(
        [
            f"SELECT '{severity}'::varchar AS severity, {response}::int AS response_sla_hours, {resolution}::int AS resolution_sla_hours"
            for severity, response, resolution in DEFAULT_SLA_POLICIES
        ]
    )
    op.execute(
        sa.text(
            f"""
            INSERT INTO issue_sla_policies (
                id,
                organization_id,
                severity,
                response_sla_hours,
                resolution_sla_hours,
                created_at,
                updated_at
            )
            SELECT
                gen_random_uuid(),
                org.id,
                policy.severity,
                policy.response_sla_hours,
                policy.resolution_sla_hours,
                now(),
                now()
            FROM organizations AS org
            CROSS JOIN (
                {values_sql}
            ) AS policy
            ON CONFLICT (organization_id, severity) DO NOTHING
            """
        )
    )

    op.create_table(
        "issue_sla_tracking",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("issue_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("response_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolution_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("response_met_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_met_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("response_breached", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("resolution_breached", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["issue_id"], ["issues.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("issue_id", name="uq_issue_sla_tracking_issue_id"),
    )
    op.create_index("ix_issue_sla_tracking_issue_id", "issue_sla_tracking", ["issue_id"], unique=False)
    op.create_index(
        "ix_issue_sla_tracking_org_response_breached",
        "issue_sla_tracking",
        ["organization_id", "response_breached"],
        unique=False,
    )
    op.create_index(
        "ix_issue_sla_tracking_org_resolution_breached",
        "issue_sla_tracking",
        ["organization_id", "resolution_breached"],
        unique=False,
    )
    op.create_index(
        "ix_issue_sla_tracking_response_deadline",
        "issue_sla_tracking",
        ["response_deadline", "response_breached"],
        unique=False,
    )
    op.create_index(
        "ix_issue_sla_tracking_resolution_deadline",
        "issue_sla_tracking",
        ["resolution_deadline", "resolution_breached"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_issue_sla_tracking_resolution_deadline", table_name="issue_sla_tracking")
    op.drop_index("ix_issue_sla_tracking_response_deadline", table_name="issue_sla_tracking")
    op.drop_index("ix_issue_sla_tracking_org_resolution_breached", table_name="issue_sla_tracking")
    op.drop_index("ix_issue_sla_tracking_org_response_breached", table_name="issue_sla_tracking")
    op.drop_index("ix_issue_sla_tracking_issue_id", table_name="issue_sla_tracking")
    op.drop_table("issue_sla_tracking")

    op.drop_table("issue_sla_policies")

    op.drop_index("ix_root_cause_analyses_org_authored", table_name="root_cause_analyses")
    op.drop_index("ix_root_cause_analyses_org_issue", table_name="root_cause_analyses")
    op.drop_table("root_cause_analyses")
