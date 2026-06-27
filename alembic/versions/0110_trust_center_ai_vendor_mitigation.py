"""trust center, ai vendor assessments, and vendor mitigation workflow

Revision ID: 0110_trust_center_ai_vendor_mitigation
Revises: 0109_subprocessors_and_customer_commitments
Create Date: 2026-06-24 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0110_trust_center_ai_vendor_mitigation"
down_revision: str | None = "0109_subprocessors_and_customer_commitments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("organizations", "slug", existing_type=sa.String(length=120), type_=sa.String(length=100), nullable=True)
    op.drop_index("ix_organizations_slug", table_name="organizations")
    op.create_index(
        "ix_organizations_slug",
        "organizations",
        ["slug"],
        unique=True,
        postgresql_where=sa.text("slug IS NOT NULL"),
    )

    op.create_table(
        "trust_center_configurations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("tagline", sa.Text(), nullable=True),
        sa.Column("logo_url", sa.String(length=500), nullable=True),
        sa.Column("show_certifications", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("show_framework_coverage", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("show_published_policies", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("show_uptime_status", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("uptime_status", sa.String(length=50), nullable=True),
        sa.Column("uptime_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("contact_email", sa.String(length=255), nullable=True),
        sa.Column("request_access_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("custom_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "uptime_status IN ('operational', 'degraded', 'partial_outage', 'major_outage', 'maintenance') OR uptime_status IS NULL",
            name="ck_trust_center_configurations_uptime_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", name="uq_trust_center_configurations_organization_id"),
    )

    op.create_table(
        "trust_center_access_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requester_name", sa.String(length=255), nullable=False),
        sa.Column("requester_email", sa.String(length=255), nullable=False),
        sa.Column("requester_company", sa.String(length=255), nullable=True),
        sa.Column("request_reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("access_token_hash", sa.String(length=64), nullable=True),
        sa.Column("access_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'expired')",
            name="ck_trust_center_access_requests_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_trust_center_access_requests_org_status",
        "trust_center_access_requests",
        ["organization_id", "status"],
        unique=False,
    )

    op.create_table(
        "trust_center_published_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("published_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["policy_id"], ["compliance_policies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["published_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "policy_id", name="uq_trust_center_published_policies_org_policy"),
    )
    op.create_index(
        "ix_trust_center_published_policies_org_active",
        "trust_center_published_policies",
        ["organization_id", "is_active"],
        unique=False,
    )

    op.create_table(
        "ai_vendor_assessments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assessor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("ai_model_name", sa.String(length=255), nullable=True),
        sa.Column("ai_model_version", sa.String(length=100), nullable=True),
        sa.Column("ai_model_provider", sa.String(length=255), nullable=True),
        sa.Column("model_type", sa.String(length=100), nullable=True),
        sa.Column("training_data_source", sa.Text(), nullable=True),
        sa.Column("training_data_governance", sa.Text(), nullable=True),
        sa.Column("data_exits_environment", sa.Boolean(), nullable=True),
        sa.Column("data_exits_details", sa.Text(), nullable=True),
        sa.Column("bias_testing_performed", sa.Boolean(), nullable=True),
        sa.Column("bias_testing_method", sa.Text(), nullable=True),
        sa.Column("bias_testing_frequency", sa.String(length=100), nullable=True),
        sa.Column("explainability_approach", sa.Text(), nullable=True),
        sa.Column("human_oversight_required", sa.Boolean(), nullable=True),
        sa.Column("human_oversight_details", sa.Text(), nullable=True),
        sa.Column("output_used_for_decisions", sa.Boolean(), nullable=True),
        sa.Column("decision_types", sa.Text(), nullable=True),
        sa.Column("regulatory_obligations", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("vendor_ai_policy_url", sa.String(length=500), nullable=True),
        sa.Column("incident_history", sa.Text(), nullable=True),
        sa.Column("overall_risk_level", sa.String(length=20), nullable=True),
        sa.Column("risk_score", sa.Integer(), nullable=True),
        sa.Column("assessor_notes", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('draft', 'in_progress', 'completed', 'archived')",
            name="ck_ai_vendor_assessments_status",
        ),
        sa.CheckConstraint(
            "model_type IN ('llm', 'ml_classifier', 'computer_vision', 'nlp', 'recommendation', 'generative', 'other') OR model_type IS NULL",
            name="ck_ai_vendor_assessments_model_type",
        ),
        sa.CheckConstraint(
            "overall_risk_level IN ('low', 'medium', 'high', 'critical') OR overall_risk_level IS NULL",
            name="ck_ai_vendor_assessments_overall_risk_level",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assessor_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_vendor_assessments_org_vendor", "ai_vendor_assessments", ["organization_id", "vendor_id"], unique=False)
    op.create_index("ix_ai_vendor_assessments_org_status", "ai_vendor_assessments", ["organization_id", "status"], unique=False)
    op.create_index(
        "ix_ai_vendor_assessments_org_risk_level",
        "ai_vendor_assessments",
        ["organization_id", "overall_risk_level"],
        unique=False,
    )

    op.create_table(
        "vendor_mitigation_cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assessment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ai_assessment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default=sa.text("'open'")),
        sa.Column("assigned_owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("closure_notes", sa.Text(), nullable=True),
        sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("escalated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("escalation_reason", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "severity IN ('critical', 'high', 'medium', 'low')",
            name="ck_vendor_mitigation_cases_severity",
        ),
        sa.CheckConstraint(
            "status IN ('open', 'in_progress', 'pending_vendor_evidence', 'under_review', 'closed', 'escalated', 'cancelled')",
            name="ck_vendor_mitigation_cases_status",
        ),
        sa.CheckConstraint(
            "assessment_id IS NOT NULL OR ai_assessment_id IS NOT NULL",
            name="ck_vendor_mitigation_cases_assessment_required",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assessment_id"], ["vendor_assessments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["ai_assessment_id"], ["ai_vendor_assessments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assigned_owner_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["closed_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["escalated_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vendor_mitigation_cases_org_vendor", "vendor_mitigation_cases", ["organization_id", "vendor_id"], unique=False)
    op.create_index(
        "ix_vendor_mitigation_cases_org_status_severity",
        "vendor_mitigation_cases",
        ["organization_id", "status", "severity"],
        unique=False,
    )
    op.create_index("ix_vendor_mitigation_cases_due_status", "vendor_mitigation_cases", ["due_date", "status"], unique=False)

    op.create_table(
        "vendor_mitigation_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("action_type", sa.String(length=100), nullable=False),
        sa.Column("assigned_to_vendor", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default=sa.text("'open'")),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("evidence_submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "action_type IN ('policy_update', 'technical_control', 'training', 'documentation', 'audit', 'contract_amendment', 'custom')",
            name="ck_vendor_mitigation_actions_action_type",
        ),
        sa.CheckConstraint(
            "status IN ('open', 'in_progress', 'evidence_submitted', 'accepted', 'rejected', 'overdue')",
            name="ck_vendor_mitigation_actions_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["case_id"], ["vendor_mitigation_cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence_items.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["accepted_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["rejected_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vendor_mitigation_actions_case_id", "vendor_mitigation_actions", ["case_id"], unique=False)
    op.create_index("ix_vendor_mitigation_actions_org_status", "vendor_mitigation_actions", ["organization_id", "status"], unique=False)
    op.create_index("ix_vendor_mitigation_actions_due_status", "vendor_mitigation_actions", ["due_date", "status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_vendor_mitigation_actions_due_status", table_name="vendor_mitigation_actions")
    op.drop_index("ix_vendor_mitigation_actions_org_status", table_name="vendor_mitigation_actions")
    op.drop_index("ix_vendor_mitigation_actions_case_id", table_name="vendor_mitigation_actions")
    op.drop_table("vendor_mitigation_actions")

    op.drop_index("ix_vendor_mitigation_cases_due_status", table_name="vendor_mitigation_cases")
    op.drop_index("ix_vendor_mitigation_cases_org_status_severity", table_name="vendor_mitigation_cases")
    op.drop_index("ix_vendor_mitigation_cases_org_vendor", table_name="vendor_mitigation_cases")
    op.drop_table("vendor_mitigation_cases")

    op.drop_index("ix_ai_vendor_assessments_org_risk_level", table_name="ai_vendor_assessments")
    op.drop_index("ix_ai_vendor_assessments_org_status", table_name="ai_vendor_assessments")
    op.drop_index("ix_ai_vendor_assessments_org_vendor", table_name="ai_vendor_assessments")
    op.drop_table("ai_vendor_assessments")

    op.drop_index("ix_trust_center_published_policies_org_active", table_name="trust_center_published_policies")
    op.drop_table("trust_center_published_policies")

    op.drop_index("ix_trust_center_access_requests_org_status", table_name="trust_center_access_requests")
    op.drop_table("trust_center_access_requests")

    op.drop_table("trust_center_configurations")

    op.drop_index("ix_organizations_slug", table_name="organizations")
    op.create_index("ix_organizations_slug", "organizations", ["slug"], unique=True)
    op.alter_column("organizations", "slug", existing_type=sa.String(length=100), type_=sa.String(length=120), nullable=False)
