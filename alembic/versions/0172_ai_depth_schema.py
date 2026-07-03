"""ai depth schema

Revision ID: 0172_ai_depth_schema
Revises: 0171_semantic_mapping
Create Date: 2026-06-29 16:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0172_ai_depth_schema"
down_revision: str | None = "0171_semantic_mapping"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


AI_SYSTEM_DEPTH_COLUMNS: list[tuple[str, sa.Column]] = [
    ("bias_assessment_status", sa.Column("bias_assessment_status", sa.VARCHAR(length=20), nullable=True)),
    ("last_bias_assessment_at", sa.Column("last_bias_assessment_at", sa.DateTime(timezone=True), nullable=True)),
    ("explainability_method", sa.Column("explainability_method", sa.VARCHAR(length=50), nullable=True)),
    ("human_oversight_level", sa.Column("human_oversight_level", sa.VARCHAR(length=20), nullable=True)),
    ("data_governance_score", sa.Column("data_governance_score", sa.Float(), nullable=True)),
    ("atlas_risk_score", sa.Column("atlas_risk_score", sa.Integer(), nullable=True)),
]


def _has_table(inspector: sa.Inspector, table_name: str) -> bool:
    return inspector.has_table(table_name)


def _has_column(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    if not inspector.has_table(table_name):
        return False
    return any(col.get("name") == column_name for col in inspector.get_columns(table_name))


def _has_index(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    if not inspector.has_table(table_name):
        return False
    return any(item.get("name") == index_name for item in inspector.get_indexes(table_name))


def _has_constraint(inspector: sa.Inspector, table_name: str, constraint_name: str) -> bool:
    if not inspector.has_table(table_name):
        return False
    return any(item.get("name") == constraint_name for item in inspector.get_check_constraints(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "ai_systems"):
        for column_name, column in AI_SYSTEM_DEPTH_COLUMNS:
            if not _has_column(inspector, "ai_systems", column_name):
                op.add_column("ai_systems", column)

        inspector = sa.inspect(bind)
        if not _has_constraint(inspector, "ai_systems", "ck_ai_systems_bias_assessment_status"):
            op.create_check_constraint(
                "ck_ai_systems_bias_assessment_status",
                "ai_systems",
                "bias_assessment_status IS NULL OR bias_assessment_status IN ('not_started', 'in_progress', 'completed', 'remediation_needed')",
            )

        inspector = sa.inspect(bind)
        if not _has_constraint(inspector, "ai_systems", "ck_ai_systems_explainability_method"):
            op.create_check_constraint(
                "ck_ai_systems_explainability_method",
                "ai_systems",
                "explainability_method IS NULL OR explainability_method IN ('shap', 'lime', 'integrated_gradients', 'counterfactual', 'rule_based', 'none')",
            )

        inspector = sa.inspect(bind)
        if not _has_constraint(inspector, "ai_systems", "ck_ai_systems_human_oversight_level"):
            op.create_check_constraint(
                "ck_ai_systems_human_oversight_level",
                "ai_systems",
                "human_oversight_level IS NULL OR human_oversight_level IN ('full_automation', 'human_on_loop', 'human_in_loop', 'human_in_command')",
            )

    inspector = sa.inspect(bind)
    if not _has_table(inspector, "ai_bias_assessments"):
        op.create_table(
            "ai_bias_assessments",
            sa.Column("id", sa.Uuid(), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
            sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
            sa.Column("system_id", sa.Uuid(), sa.ForeignKey("ai_systems.id", ondelete="CASCADE"), nullable=False),
            sa.Column("assessment_method", sa.VARCHAR(length=50), nullable=False),
            sa.Column("protected_attribute", sa.VARCHAR(length=100), nullable=False),
            sa.Column("metric_name", sa.VARCHAR(length=100), nullable=False),
            sa.Column("metric_value", sa.Float(), nullable=False),
            sa.Column("threshold_value", sa.Float(), nullable=False),
            sa.Column("passed", sa.Boolean(), nullable=False),
            sa.Column("remediation_notes", sa.Text(), nullable=True),
            sa.Column("assessed_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    inspector = sa.inspect(bind)
    if not _has_index(inspector, "ai_bias_assessments", "ix_ai_bias_assessments_org_system"):
        op.create_index("ix_ai_bias_assessments_org_system", "ai_bias_assessments", ["organization_id", "system_id"], unique=False)
    if not _has_index(inspector, "ai_bias_assessments", "ix_ai_bias_assessments_system_assessed"):
        op.create_index("ix_ai_bias_assessments_system_assessed", "ai_bias_assessments", ["system_id", "assessed_at"], unique=False)
    if not _has_index(inspector, "ai_bias_assessments", "ix_ai_bias_assessments_passed"):
        op.create_index("ix_ai_bias_assessments_passed", "ai_bias_assessments", ["passed"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "ai_bias_assessments"):
        if _has_index(inspector, "ai_bias_assessments", "ix_ai_bias_assessments_passed"):
            op.drop_index("ix_ai_bias_assessments_passed", table_name="ai_bias_assessments")
        if _has_index(inspector, "ai_bias_assessments", "ix_ai_bias_assessments_system_assessed"):
            op.drop_index("ix_ai_bias_assessments_system_assessed", table_name="ai_bias_assessments")
        if _has_index(inspector, "ai_bias_assessments", "ix_ai_bias_assessments_org_system"):
            op.drop_index("ix_ai_bias_assessments_org_system", table_name="ai_bias_assessments")
        op.drop_table("ai_bias_assessments")

    inspector = sa.inspect(bind)
    if _has_table(inspector, "ai_systems"):
        if _has_constraint(inspector, "ai_systems", "ck_ai_systems_human_oversight_level"):
            op.drop_constraint("ck_ai_systems_human_oversight_level", "ai_systems", type_="check")
        if _has_constraint(inspector, "ai_systems", "ck_ai_systems_explainability_method"):
            op.drop_constraint("ck_ai_systems_explainability_method", "ai_systems", type_="check")
        if _has_constraint(inspector, "ai_systems", "ck_ai_systems_bias_assessment_status"):
            op.drop_constraint("ck_ai_systems_bias_assessment_status", "ai_systems", type_="check")

        inspector = sa.inspect(bind)
        for column_name, _ in reversed(AI_SYSTEM_DEPTH_COLUMNS):
            if _has_column(inspector, "ai_systems", column_name):
                op.drop_column("ai_systems", column_name)
            inspector = sa.inspect(bind)
