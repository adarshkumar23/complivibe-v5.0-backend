"""dpia and lawful basis registry

Revision ID: 0141_dpia_and_lawful_basis
Revises: 0140_consent_cookie_notice
Create Date: 2026-06-26 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0141_dpia_and_lawful_basis"
down_revision: str | None = "0140_consent_cookie_notice"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "dpias",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("processing_activity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("nature_of_processing", sa.Text(), nullable=True),
        sa.Column("necessity_assessment", sa.Text(), nullable=True),
        sa.Column("proportionality_assessment", sa.Text(), nullable=True),
        sa.Column("risks_identified", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("risk_assessment_notes", sa.Text(), nullable=True),
        sa.Column("mitigation_measures", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("residual_risk_level", sa.String(length=20), nullable=True),
        sa.Column("dpo_consulted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("dpo_opinion", sa.Text(), nullable=True),
        sa.Column("supervisory_authority_consulted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("sa_consultation_notes", sa.Text(), nullable=True),
        sa.Column("assigned_reviewer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_review_date", sa.Date(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('draft', 'in_progress', 'under_review', 'approved', 'rejected', 'archived')",
            name="ck_dpias_status",
        ),
        sa.CheckConstraint(
            "residual_risk_level IS NULL OR residual_risk_level IN ('low', 'medium', 'high', 'unacceptable')",
            name="ck_dpias_residual_risk_level",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["processing_activity_id"], ["processing_activities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assigned_reviewer_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_dpias_org_status", "dpias", ["organization_id", "status"], unique=False)
    op.create_index("ix_dpias_org_activity", "dpias", ["organization_id", "processing_activity_id"], unique=False)
    op.create_index("ix_dpias_org_residual_risk", "dpias", ["organization_id", "residual_risk_level"], unique=False)

    op.create_table(
        "dpia_checklist_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dpia_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("criterion_key", sa.String(length=100), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("response", sa.String(length=20), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("response IS NULL OR response IN ('yes', 'no', 'partial', 'na')", name="ck_dpia_checklist_items_response"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dpia_id"], ["dpias.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dpia_id", "criterion_key", name="uq_dpia_checklist_items_dpia_criterion"),
    )
    op.create_index("ix_dpia_checklist_org_dpia", "dpia_checklist_items", ["organization_id", "dpia_id"], unique=False)

    op.create_table(
        "lawful_basis_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("processing_activity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lawful_basis", sa.String(length=50), nullable=False),
        sa.Column("basis_description", sa.Text(), nullable=False),
        sa.Column("applicable_frameworks", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("article_reference", sa.String(length=255), nullable=True),
        sa.Column("legitimate_interest_assessment", sa.Text(), nullable=True),
        sa.Column("review_required_at", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("documented_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("documented_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "lawful_basis IN ('consent', 'contract', 'legal_obligation', 'vital_interests', 'public_task', 'legitimate_interests')",
            name="ck_lawful_basis_records_lawful_basis",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["processing_activity_id"], ["processing_activities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["documented_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "processing_activity_id",
            "lawful_basis",
            name="uq_lawful_basis_records_org_activity_basis",
        ),
    )
    op.create_index("ix_lawful_basis_org_basis", "lawful_basis_records", ["organization_id", "lawful_basis"], unique=False)
    op.create_index("ix_lawful_basis_org_activity", "lawful_basis_records", ["organization_id", "processing_activity_id"], unique=False)
    op.create_index("ix_lawful_basis_org_active", "lawful_basis_records", ["organization_id", "is_active"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_lawful_basis_org_active", table_name="lawful_basis_records")
    op.drop_index("ix_lawful_basis_org_activity", table_name="lawful_basis_records")
    op.drop_index("ix_lawful_basis_org_basis", table_name="lawful_basis_records")
    op.drop_table("lawful_basis_records")

    op.drop_index("ix_dpia_checklist_org_dpia", table_name="dpia_checklist_items")
    op.drop_table("dpia_checklist_items")

    op.drop_index("ix_dpias_org_residual_risk", table_name="dpias")
    op.drop_index("ix_dpias_org_activity", table_name="dpias")
    op.drop_index("ix_dpias_org_status", table_name="dpias")
    op.drop_table("dpias")
