"""third party ai assessments, model cards, and aibom

Revision ID: 0127_third_party_model_cards_aibom
Revises: 0126_iso42001_nist_rmf_workflows
Create Date: 2026-06-25 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0127_third_party_model_cards_aibom"
down_revision: str | None = "0126_iso42001_nist_rmf_workflows"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "third_party_ai_assessments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ai_system_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("model_version", sa.String(length=100), nullable=True),
        sa.Column("data_egress_type", sa.String(length=20), nullable=False),
        sa.Column("model_card_provided", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("bias_testing_documented", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("explainability_level", sa.String(length=50), nullable=True),
        sa.Column("contractual_ai_terms_reviewed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("eu_act_compliance_status", sa.String(length=50), nullable=True),
        sa.Column("overall_risk_level", sa.String(length=20), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("assessed_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "data_egress_type IN ('none', 'anonymized', 'identified')",
            name="ck_third_party_ai_assessments_data_egress_type",
        ),
        sa.CheckConstraint(
            "explainability_level IS NULL OR explainability_level IN ('full', 'partial', 'none', 'not_required')",
            name="ck_third_party_ai_assessments_explainability_level",
        ),
        sa.CheckConstraint(
            "eu_act_compliance_status IS NULL OR eu_act_compliance_status IN ('compliant', 'non_compliant', 'unknown', 'not_applicable')",
            name="ck_third_party_ai_assessments_eu_act_compliance_status",
        ),
        sa.CheckConstraint(
            "overall_risk_level IS NULL OR overall_risk_level IN ('low', 'medium', 'high', 'critical')",
            name="ck_third_party_ai_assessments_overall_risk_level",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'in_progress', 'completed', 'archived')",
            name="ck_third_party_ai_assessments_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assessed_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_third_party_ai_assessments_org_vendor",
        "third_party_ai_assessments",
        ["organization_id", "vendor_id"],
        unique=False,
    )
    op.create_index(
        "ix_third_party_ai_assessments_org_status",
        "third_party_ai_assessments",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_third_party_ai_assessments_org_risk",
        "third_party_ai_assessments",
        ["organization_id", "overall_risk_level"],
        unique=False,
    )

    op.create_table(
        "model_cards",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ai_system_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("intended_purpose", sa.Text(), nullable=False),
        sa.Column("training_data_description", sa.Text(), nullable=True),
        sa.Column("training_data_cutoff_date", sa.Date(), nullable=True),
        sa.Column("known_limitations", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("performance_metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("approved_use_cases", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("prohibited_use_cases", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("bias_evaluation_results", sa.Text(), nullable=True),
        sa.Column("human_oversight_requirements", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("contact_owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "status IN ('draft', 'published', 'archived')",
            name="ck_model_cards_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["contact_owner_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_model_cards_org_system_status",
        "model_cards",
        ["organization_id", "ai_system_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_model_cards_org_system_version",
        "model_cards",
        ["organization_id", "ai_system_id", "version"],
        unique=False,
    )

    op.create_table(
        "aibom_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ai_system_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("generated_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["generated_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_aibom_records_org_system", "aibom_records", ["organization_id", "ai_system_id"], unique=False)
    op.create_index(
        "ix_aibom_records_org_system_version",
        "aibom_records",
        ["organization_id", "ai_system_id", "version"],
        unique=False,
    )

    op.create_table(
        "aibom_components",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("aibom_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("component_type", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("version", sa.String(length=100), nullable=True),
        sa.Column("source", sa.String(length=500), nullable=True),
        sa.Column("license_type", sa.String(length=100), nullable=True),
        sa.Column("is_third_party", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("risk_notes", sa.Text(), nullable=True),
        sa.Column("source_integration", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "component_type IN ('training_data', 'base_model', 'fine_tuning_dataset', 'runtime_data_feed', 'third_party_api', 'framework_library')",
            name="ck_aibom_components_component_type",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["aibom_id"], ["aibom_records.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("aibom_id", "component_type", "name", name="uq_aibom_components_type_name"),
    )
    op.create_index("ix_aibom_components_aibom_id", "aibom_components", ["aibom_id"], unique=False)
    op.create_index(
        "ix_aibom_components_org_aibom_id",
        "aibom_components",
        ["organization_id", "aibom_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_aibom_components_org_aibom_id", table_name="aibom_components")
    op.drop_index("ix_aibom_components_aibom_id", table_name="aibom_components")
    op.drop_table("aibom_components")

    op.drop_index("ix_aibom_records_org_system_version", table_name="aibom_records")
    op.drop_index("ix_aibom_records_org_system", table_name="aibom_records")
    op.drop_table("aibom_records")

    op.drop_index("ix_model_cards_org_system_version", table_name="model_cards")
    op.drop_index("ix_model_cards_org_system_status", table_name="model_cards")
    op.drop_table("model_cards")

    op.drop_index("ix_third_party_ai_assessments_org_risk", table_name="third_party_ai_assessments")
    op.drop_index("ix_third_party_ai_assessments_org_status", table_name="third_party_ai_assessments")
    op.drop_index("ix_third_party_ai_assessments_org_vendor", table_name="third_party_ai_assessments")
    op.drop_table("third_party_ai_assessments")
