"""eu ai act workflows and ai risk assessments

Revision ID: 0125_eu_act_workflows_and_ai_risk_assessments
Revises: 0124_ai_governance_reviews_classification_eu_act
Create Date: 2026-06-25 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0125_eu_act_workflows_and_ai_risk_assessments"
down_revision: str | None = "0124_ai_governance_reviews_classification_eu_act"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "eu_act_conformity_assessments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ai_system_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assessment_type", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("technical_documentation_complete", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("qms_compliant", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("human_oversight_measures", sa.Text(), nullable=True),
        sa.Column("accuracy_robustness_measures", sa.Text(), nullable=True),
        sa.Column("checklist_items", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "assessment_type IN ('self_assessment', 'notified_body')",
            name="ck_eu_act_conformity_assessments_type",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'in_progress', 'complete', 'submitted')",
            name="ck_eu_act_conformity_assessments_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_eu_act_conformity_assessments_org_system",
        "eu_act_conformity_assessments",
        ["organization_id", "ai_system_id"],
        unique=False,
    )
    op.create_index(
        "ix_eu_act_conformity_assessments_org_status",
        "eu_act_conformity_assessments",
        ["organization_id", "status"],
        unique=False,
    )

    op.create_table(
        "eu_act_frias",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ai_system_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rights_affected", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("risk_to_rights_assessment", sa.Text(), nullable=True),
        sa.Column("mitigation_measures", sa.Text(), nullable=True),
        sa.Column("consultation_conducted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "status IN ('draft', 'in_progress', 'complete')",
            name="ck_eu_act_frias_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_eu_act_frias_org_system", "eu_act_frias", ["organization_id", "ai_system_id"], unique=False)
    op.create_index("ix_eu_act_frias_org_status", "eu_act_frias", ["organization_id", "status"], unique=False)

    op.create_table(
        "eu_act_post_market_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ai_system_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("monitoring_metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("reporting_frequency", sa.String(length=50), nullable=True),
        sa.Column("incident_reporting_threshold", sa.Text(), nullable=True),
        sa.Column("responsible_person_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "reporting_frequency IS NULL OR reporting_frequency IN ('monthly', 'quarterly', 'annually')",
            name="ck_eu_act_post_market_plans_reporting_frequency",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'archived')",
            name="ck_eu_act_post_market_plans_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["responsible_person_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_eu_act_post_market_plans_org_system",
        "eu_act_post_market_plans",
        ["organization_id", "ai_system_id"],
        unique=False,
    )
    op.create_index(
        "ix_eu_act_post_market_plans_org_status",
        "eu_act_post_market_plans",
        ["organization_id", "status"],
        unique=False,
    )

    op.create_table(
        "ai_risk_assessment_questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("risk_dimension", sa.String(length=50), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("weight", sa.Numeric(4, 2), nullable=False, server_default=sa.text("1.0")),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.CheckConstraint(
            "risk_dimension IN ('bias', 'fairness', 'explainability', 'privacy', 'misuse', 'security')",
            name="ck_ai_risk_assessment_questions_dimension",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_risk_assessment_questions_dimension_order",
        "ai_risk_assessment_questions",
        ["risk_dimension", "order_index"],
        unique=False,
    )

    op.create_table(
        "ai_risk_assessments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ai_system_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assessment_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("bias_risk_rating", sa.String(length=20), nullable=True),
        sa.Column("fairness_risk_rating", sa.String(length=20), nullable=True),
        sa.Column("explainability_risk_rating", sa.String(length=20), nullable=True),
        sa.Column("privacy_risk_rating", sa.String(length=20), nullable=True),
        sa.Column("misuse_risk_rating", sa.String(length=20), nullable=True),
        sa.Column("security_risk_rating", sa.String(length=20), nullable=True),
        sa.Column("overall_risk_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("assessment_bias_results", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("completed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "status IN ('draft', 'in_progress', 'completed', 'archived')",
            name="ck_ai_risk_assessments_status",
        ),
        sa.CheckConstraint(
            "bias_risk_rating IS NULL OR bias_risk_rating IN ('low', 'medium', 'high', 'critical')",
            name="ck_ai_risk_assessments_bias_rating",
        ),
        sa.CheckConstraint(
            "fairness_risk_rating IS NULL OR fairness_risk_rating IN ('low', 'medium', 'high', 'critical')",
            name="ck_ai_risk_assessments_fairness_rating",
        ),
        sa.CheckConstraint(
            "explainability_risk_rating IS NULL OR explainability_risk_rating IN ('low', 'medium', 'high', 'critical')",
            name="ck_ai_risk_assessments_explainability_rating",
        ),
        sa.CheckConstraint(
            "privacy_risk_rating IS NULL OR privacy_risk_rating IN ('low', 'medium', 'high', 'critical')",
            name="ck_ai_risk_assessments_privacy_rating",
        ),
        sa.CheckConstraint(
            "misuse_risk_rating IS NULL OR misuse_risk_rating IN ('low', 'medium', 'high', 'critical')",
            name="ck_ai_risk_assessments_misuse_rating",
        ),
        sa.CheckConstraint(
            "security_risk_rating IS NULL OR security_risk_rating IN ('low', 'medium', 'high', 'critical')",
            name="ck_ai_risk_assessments_security_rating",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["completed_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_risk_assessments_org_system", "ai_risk_assessments", ["organization_id", "ai_system_id"], unique=False)
    op.create_index("ix_ai_risk_assessments_org_status", "ai_risk_assessments", ["organization_id", "status"], unique=False)

    op.create_table(
        "ai_risk_assessment_responses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assessment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("response", sa.String(length=20), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("risk_contribution", sa.Numeric(5, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "response IS NULL OR response IN ('low_risk', 'medium_risk', 'high_risk', 'critical_risk')",
            name="ck_ai_risk_assessment_responses_response",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assessment_id"], ["ai_risk_assessments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["question_id"], ["ai_risk_assessment_questions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("assessment_id", "question_id", name="uq_ai_risk_assessment_response_question"),
    )
    op.create_index("ix_ai_risk_assessment_responses_assessment", "ai_risk_assessment_responses", ["assessment_id"], unique=False)
    op.create_index(
        "ix_ai_risk_assessment_responses_org_assessment",
        "ai_risk_assessment_responses",
        ["organization_id", "assessment_id"],
        unique=False,
    )

    questions = [
        # bias
        ("bias", "Does the training data represent all affected demographic groups proportionally?", 0),
        ("bias", "Has the model been tested for disparate error rates across demographic groups?", 1),
        ("bias", "Are historical biases in the training data identified and documented?", 2),
        ("bias", "Is bias testing repeated after any model update or retraining?", 3),
        ("bias", "Is there a process to receive and investigate bias complaints?", 4),
        # fairness
        ("fairness", "Does the system produce equal-quality outcomes across protected attributes?", 0),
        ("fairness", "Have fairness metrics (e.g. demographic parity) been computed and documented?", 1),
        ("fairness", "Is the fairness threshold for this system defined and agreed with stakeholders?", 2),
        ("fairness", "Are there counterfactual fairness tests for individual-level decisions?", 3),
        ("fairness", "Is fairness evaluated periodically in production, not just at deployment?", 4),
        # explainability
        ("explainability", "Can the system provide a human-readable explanation for its outputs?", 0),
        ("explainability", "Are explanations available for all high-stakes decisions?", 1),
        ("explainability", "Do explanations include the most influential features or factors?", 2),
        ("explainability", "Are explanations validated to be faithful to the model's actual logic?", 3),
        ("explainability", "Can a non-technical stakeholder understand the explanation?", 4),
        # privacy
        ("privacy", "Is a Data Protection Impact Assessment (DPIA) completed for this system?", 0),
        ("privacy", "Does the system process special category personal data (health, ethnicity, biometric)?", 1),
        ("privacy", "Is data minimization applied - only necessary data is processed?", 2),
        ("privacy", "Are data retention periods defined and enforced for training and inference data?", 3),
        ("privacy", "Are data subject rights (access, deletion, objection) implementable for this system?", 4),
        # misuse
        ("misuse", "Are there documented prohibited uses for this AI system?", 0),
        ("misuse", "Is access to the system controlled to prevent unauthorized use?", 1),
        ("misuse", "Could the system be repurposed for surveillance, manipulation, or discrimination?", 2),
        ("misuse", "Are misuse detection mechanisms in place?", 3),
        ("misuse", "Is there an incident response process specific to AI misuse events?", 4),
        # security
        ("security", "Has the system been tested for adversarial attacks (e.g. prompt injection, data poisoning)?", 0),
        ("security", "Are model weights and training artifacts stored securely with access controls?", 1),
        ("security", "Is the supply chain for third-party models and datasets verified?", 2),
        ("security", "Are model inference endpoints protected against denial-of-service attacks?", 3),
        ("security", "Is model versioning and rollback capability available?", 4),
    ]
    question_rows = [
        {
            "risk_dimension": dimension,
            "question_text": text,
            "weight": 1.0,
            "order_index": order_idx,
            "is_active": True,
        }
        for dimension, text, order_idx in questions
    ]

    table = sa.table(
        "ai_risk_assessment_questions",
        sa.column("risk_dimension", sa.String(length=50)),
        sa.column("question_text", sa.Text()),
        sa.column("weight", sa.Numeric(4, 2)),
        sa.column("order_index", sa.Integer()),
        sa.column("is_active", sa.Boolean()),
    )
    op.bulk_insert(table, question_rows)


def downgrade() -> None:
    op.drop_index("ix_ai_risk_assessment_responses_org_assessment", table_name="ai_risk_assessment_responses")
    op.drop_index("ix_ai_risk_assessment_responses_assessment", table_name="ai_risk_assessment_responses")
    op.drop_table("ai_risk_assessment_responses")

    op.drop_index("ix_ai_risk_assessments_org_status", table_name="ai_risk_assessments")
    op.drop_index("ix_ai_risk_assessments_org_system", table_name="ai_risk_assessments")
    op.drop_table("ai_risk_assessments")

    op.drop_index("ix_ai_risk_assessment_questions_dimension_order", table_name="ai_risk_assessment_questions")
    op.drop_table("ai_risk_assessment_questions")

    op.drop_index("ix_eu_act_post_market_plans_org_status", table_name="eu_act_post_market_plans")
    op.drop_index("ix_eu_act_post_market_plans_org_system", table_name="eu_act_post_market_plans")
    op.drop_table("eu_act_post_market_plans")

    op.drop_index("ix_eu_act_frias_org_status", table_name="eu_act_frias")
    op.drop_index("ix_eu_act_frias_org_system", table_name="eu_act_frias")
    op.drop_table("eu_act_frias")

    op.drop_index("ix_eu_act_conformity_assessments_org_status", table_name="eu_act_conformity_assessments")
    op.drop_index("ix_eu_act_conformity_assessments_org_system", table_name="eu_act_conformity_assessments")
    op.drop_table("eu_act_conformity_assessments")
