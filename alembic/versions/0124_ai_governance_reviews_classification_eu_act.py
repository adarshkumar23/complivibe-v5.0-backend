"""ai governance reviews classification and eu ai act

Revision ID: 0124_ai_governance_reviews_classification_eu_act
Revises: 0123_ai_governance_inventory_shadow_usecases
Create Date: 2026-06-25 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0124_ai_governance_reviews_classification_eu_act"
down_revision: str | None = "0123_ai_governance_inventory_shadow_usecases"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_governance_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ai_system_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("review_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("assigned_reviewer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_notes", sa.Text(), nullable=True),
        sa.Column("conditions", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "review_type IN ('initial_approval', 'periodic', 'triggered', 'pre_deployment')",
            name="ck_ai_governance_reviews_review_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'in_review', 'approved', 'rejected', 'conditional')",
            name="ck_ai_governance_reviews_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assigned_reviewer_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_governance_reviews_org_system",
        "ai_governance_reviews",
        ["organization_id", "ai_system_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_ai_governance_reviews_org_reviewer_status",
        "ai_governance_reviews",
        ["organization_id", "assigned_reviewer_id", "status"],
        unique=False,
    )

    op.create_table(
        "ai_review_criteria_responses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("review_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("criterion_key", sa.String(length=100), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("response", sa.String(length=20), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "response IS NULL OR response IN ('yes', 'no', 'partial', 'na')",
            name="ck_ai_review_criteria_responses_response",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["review_id"], ["ai_governance_reviews.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("review_id", "criterion_key", name="uq_ai_review_criteria_review_key"),
    )
    op.create_index("ix_ai_review_criteria_review", "ai_review_criteria_responses", ["review_id"], unique=False)

    op.create_table(
        "ai_risk_classifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ai_system_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("risk_tier", sa.String(length=20), nullable=False),
        sa.Column("classification_method", sa.String(length=20), nullable=False),
        sa.Column("classification_basis", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("classified_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("classified_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("review_required_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("risk_tier IN ('prohibited', 'high', 'limited', 'minimal')", name="ck_ai_risk_classifications_tier"),
        sa.CheckConstraint("classification_method IN ('guided', 'manual', 'auto')", name="ck_ai_risk_classifications_method"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["classified_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ai_system_id", name="uq_ai_risk_classifications_system_id"),
    )
    op.create_index(
        "ix_ai_risk_classifications_org_tier",
        "ai_risk_classifications",
        ["organization_id", "risk_tier"],
        unique=False,
    )

    op.create_table(
        "eu_act_annex_mappings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("annex_ref", sa.String(length=20), nullable=False),
        sa.Column("annex_type", sa.String(length=20), nullable=False),
        sa.Column("sector", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("article_refs", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.CheckConstraint("annex_type IN ('annex_i', 'annex_iii')", name="ck_eu_act_annex_mappings_type"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("annex_ref", name="uq_eu_act_annex_ref"),
    )
    op.create_index("ix_eu_act_annex_mappings_ref", "eu_act_annex_mappings", ["annex_ref"], unique=False)

    op.create_table(
        "eu_ai_act_classifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ai_system_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("article_category", sa.String(length=50), nullable=False),
        sa.Column("annex_reference", sa.String(length=20), nullable=True),
        sa.Column("conformity_route", sa.String(length=30), nullable=True),
        sa.Column("registration_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("transparency_obligations", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("classified_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("classified_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "article_category IN ('prohibited', 'high_risk_annex1', 'high_risk_annex3', 'limited_risk', 'minimal_risk')",
            name="ck_eu_ai_act_classifications_category",
        ),
        sa.CheckConstraint(
            "conformity_route IS NULL OR conformity_route IN ('self_assessment', 'notified_body')",
            name="ck_eu_ai_act_classifications_route",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["classified_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ai_system_id", name="uq_eu_ai_act_classifications_system_id"),
    )
    op.create_index(
        "ix_eu_ai_act_classifications_org_category",
        "eu_ai_act_classifications",
        ["organization_id", "article_category"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_eu_ai_act_classifications_org_category", table_name="eu_ai_act_classifications")
    op.drop_table("eu_ai_act_classifications")

    op.drop_index("ix_eu_act_annex_mappings_ref", table_name="eu_act_annex_mappings")
    op.drop_table("eu_act_annex_mappings")

    op.drop_index("ix_ai_risk_classifications_org_tier", table_name="ai_risk_classifications")
    op.drop_table("ai_risk_classifications")

    op.drop_index("ix_ai_review_criteria_review", table_name="ai_review_criteria_responses")
    op.drop_table("ai_review_criteria_responses")

    op.drop_index("ix_ai_governance_reviews_org_reviewer_status", table_name="ai_governance_reviews")
    op.drop_index("ix_ai_governance_reviews_org_system", table_name="ai_governance_reviews")
    op.drop_table("ai_governance_reviews")
