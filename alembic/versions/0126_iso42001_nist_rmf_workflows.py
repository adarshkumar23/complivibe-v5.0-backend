"""iso 42001 and nist ai rmf workflows

Revision ID: 0126_iso42001_nist_rmf_workflows
Revises: 0125_eu_act_workflows_and_ai_risk_assessments
Create Date: 2026-06-25 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0126_iso42001_nist_rmf_workflows"
down_revision: str | None = "0125_eu_act_workflows_and_ai_risk_assessments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "iso42001_conformity_trackers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("clause_ref", sa.String(length=20), nullable=False),
        sa.Column(
            "implementation_status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'not_started'"),
        ),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "implementation_status IN ('not_started', 'in_progress', 'implemented', 'verified')",
            name="ck_iso42001_conformity_trackers_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "clause_ref", name="uq_iso42001_conformity_trackers_org_clause"),
    )
    op.create_index(
        "ix_iso42001_conformity_trackers_org_clause",
        "iso42001_conformity_trackers",
        ["organization_id", "clause_ref"],
        unique=False,
    )

    op.create_table(
        "nist_ai_rmf_implementations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ai_system_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("govern_status", sa.String(length=20), nullable=False, server_default=sa.text("'not_started'")),
        sa.Column("map_status", sa.String(length=20), nullable=False, server_default=sa.text("'not_started'")),
        sa.Column("measure_status", sa.String(length=20), nullable=False, server_default=sa.text("'not_started'")),
        sa.Column("manage_status", sa.String(length=20), nullable=False, server_default=sa.text("'not_started'")),
        sa.Column("last_updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "govern_status IN ('not_started', 'in_progress', 'implemented')",
            name="ck_nist_ai_rmf_implementations_govern_status",
        ),
        sa.CheckConstraint(
            "map_status IN ('not_started', 'in_progress', 'implemented')",
            name="ck_nist_ai_rmf_implementations_map_status",
        ),
        sa.CheckConstraint(
            "measure_status IN ('not_started', 'in_progress', 'implemented')",
            name="ck_nist_ai_rmf_implementations_measure_status",
        ),
        sa.CheckConstraint(
            "manage_status IN ('not_started', 'in_progress', 'implemented')",
            name="ck_nist_ai_rmf_implementations_manage_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "ai_system_id", name="uq_nist_ai_rmf_implementations_org_system"),
    )
    op.create_index(
        "ix_nist_ai_rmf_implementations_org_system",
        "nist_ai_rmf_implementations",
        ["organization_id", "ai_system_id"],
        unique=False,
    )

    op.create_table(
        "ai_rmf_function_responses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("implementation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("function", sa.String(length=20), nullable=False),
        sa.Column("subcategory_ref", sa.String(length=30), nullable=False),
        sa.Column("response_status", sa.String(length=20), nullable=False, server_default=sa.text("'not_addressed'")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "function IN ('govern', 'map', 'measure', 'manage')",
            name="ck_ai_rmf_function_responses_function",
        ),
        sa.CheckConstraint(
            "response_status IN ('not_addressed', 'partial', 'implemented')",
            name="ck_ai_rmf_function_responses_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["implementation_id"],
            ["nist_ai_rmf_implementations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("implementation_id", "subcategory_ref", name="uq_ai_rmf_function_responses_impl_subcategory"),
    )
    op.create_index(
        "ix_ai_rmf_function_responses_impl_function",
        "ai_rmf_function_responses",
        ["implementation_id", "function"],
        unique=False,
    )
    op.create_index(
        "ix_ai_rmf_function_responses_org_impl",
        "ai_rmf_function_responses",
        ["organization_id", "implementation_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ai_rmf_function_responses_org_impl", table_name="ai_rmf_function_responses")
    op.drop_index("ix_ai_rmf_function_responses_impl_function", table_name="ai_rmf_function_responses")
    op.drop_table("ai_rmf_function_responses")

    op.drop_index("ix_nist_ai_rmf_implementations_org_system", table_name="nist_ai_rmf_implementations")
    op.drop_table("nist_ai_rmf_implementations")

    op.drop_index("ix_iso42001_conformity_trackers_org_clause", table_name="iso42001_conformity_trackers")
    op.drop_table("iso42001_conformity_trackers")
