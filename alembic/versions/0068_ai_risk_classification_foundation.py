"""ai risk classification foundation

Revision ID: 0068_ai_risk_classification_foundation
Revises: 0067_ai_risk_dimension_templates
Create Date: 2026-06-20 19:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0068_ai_risk_classification_foundation"
down_revision: str | None = "0067_ai_risk_dimension_templates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_system_risk_classification_taxonomy_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("taxonomy_json", sa.JSON(), nullable=False),
        sa.Column("methodology_version", sa.String(length=64), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["archived_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_system_risk_class_taxonomy_tpls_org_id_ed3c6069",
        "ai_system_risk_classification_taxonomy_templates",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_risk_classification_taxonomies_org_status",
        "ai_system_risk_classification_taxonomy_templates",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_ai_risk_classification_taxonomies_org_default",
        "ai_system_risk_classification_taxonomy_templates",
        ["organization_id", "is_default"],
        unique=False,
    )
    op.create_index(
        "ix_ai_risk_classification_taxonomies_org_archived",
        "ai_system_risk_classification_taxonomy_templates",
        ["organization_id", "archived_at"],
        unique=False,
    )

    op.create_table(
        "ai_system_risk_classification_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ai_system_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("risk_assessment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("taxonomy_template_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("taxonomy_template_snapshot_json", sa.JSON(), nullable=True),
        sa.Column("classification_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("confidence_level", sa.String(length=32), nullable=False),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=True),
        sa.Column("source_reference", sa.Text(), nullable=True),
        sa.Column("evidence_ids_json", sa.JSON(), nullable=True),
        sa.Column("control_ids_json", sa.JSON(), nullable=True),
        sa.Column("risk_ids_json", sa.JSON(), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["risk_assessment_id"], ["ai_system_risk_assessments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["taxonomy_template_id"],
            ["ai_system_risk_classification_taxonomy_templates.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["archived_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_system_risk_classification_records_organization_id",
        "ai_system_risk_classification_records",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_risk_classification_records_org_assessment",
        "ai_system_risk_classification_records",
        ["organization_id", "risk_assessment_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_risk_classification_records_org_ai_system",
        "ai_system_risk_classification_records",
        ["organization_id", "ai_system_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_risk_classification_records_org_status",
        "ai_system_risk_classification_records",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_ai_risk_classification_records_org_confidence",
        "ai_system_risk_classification_records",
        ["organization_id", "confidence_level"],
        unique=False,
    )
    op.create_index(
        "ix_ai_risk_classification_records_org_source",
        "ai_system_risk_classification_records",
        ["organization_id", "source_type"],
        unique=False,
    )
    op.create_index(
        "ix_ai_risk_classification_records_org_archived",
        "ai_system_risk_classification_records",
        ["organization_id", "archived_at"],
        unique=False,
    )

    op.add_column("ai_system_risk_assessments", sa.Column("latest_classification_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("ai_system_risk_assessments", sa.Column("classification_status", sa.String(length=32), nullable=True))
    op.add_column("ai_system_risk_assessments", sa.Column("classification_summary_json", sa.JSON(), nullable=True))
    op.create_foreign_key(
        "fk_ai_system_risk_assessments_latest_classification_id",
        "ai_system_risk_assessments",
        "ai_system_risk_classification_records",
        ["latest_classification_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_ai_system_risk_assessments_org_latest_classification",
        "ai_system_risk_assessments",
        ["organization_id", "latest_classification_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ai_system_risk_assessments_org_latest_classification", table_name="ai_system_risk_assessments")
    op.drop_constraint(
        "fk_ai_system_risk_assessments_latest_classification_id",
        "ai_system_risk_assessments",
        type_="foreignkey",
    )
    op.drop_column("ai_system_risk_assessments", "classification_summary_json")
    op.drop_column("ai_system_risk_assessments", "classification_status")
    op.drop_column("ai_system_risk_assessments", "latest_classification_id")

    op.drop_index("ix_ai_risk_classification_records_org_archived", table_name="ai_system_risk_classification_records")
    op.drop_index("ix_ai_risk_classification_records_org_source", table_name="ai_system_risk_classification_records")
    op.drop_index("ix_ai_risk_classification_records_org_confidence", table_name="ai_system_risk_classification_records")
    op.drop_index("ix_ai_risk_classification_records_org_status", table_name="ai_system_risk_classification_records")
    op.drop_index("ix_ai_risk_classification_records_org_ai_system", table_name="ai_system_risk_classification_records")
    op.drop_index("ix_ai_risk_classification_records_org_assessment", table_name="ai_system_risk_classification_records")
    op.drop_index("ix_ai_system_risk_classification_records_organization_id", table_name="ai_system_risk_classification_records")
    op.drop_table("ai_system_risk_classification_records")

    op.drop_index("ix_ai_risk_classification_taxonomies_org_archived", table_name="ai_system_risk_classification_taxonomy_templates")
    op.drop_index("ix_ai_risk_classification_taxonomies_org_default", table_name="ai_system_risk_classification_taxonomy_templates")
    op.drop_index("ix_ai_risk_classification_taxonomies_org_status", table_name="ai_system_risk_classification_taxonomy_templates")
    op.drop_index(
        "ix_ai_system_risk_class_taxonomy_tpls_org_id_ed3c6069",
        table_name="ai_system_risk_classification_taxonomy_templates",
    )
    op.drop_table("ai_system_risk_classification_taxonomy_templates")
