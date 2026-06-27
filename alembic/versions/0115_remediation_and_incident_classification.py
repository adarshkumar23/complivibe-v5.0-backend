"""remediation suggestions and incident classification

Revision ID: 0115_remediation_and_incident_classification
Revises: 0114_issue_policy_and_control_links
Create Date: 2026-06-25 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0115_remediation_and_incident_classification"
down_revision: str | None = "0114_issue_policy_and_control_links"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "remediation_suggestions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("issue_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("suggestion_text", sa.Text(), nullable=False),
        sa.Column("suggestion_source", sa.String(length=50), nullable=False),
        sa.Column("source_key", sa.String(length=255), nullable=False),
        sa.Column("applied", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("dismissed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("suggestion_source IN ('rule_based', 'template')", name="ck_remediation_suggestions_source"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["issue_id"], ["issues.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_remediation_suggestions_org_issue",
        "remediation_suggestions",
        ["organization_id", "issue_id"],
        unique=False,
    )
    op.create_index(
        "ix_remediation_suggestions_org_applied",
        "remediation_suggestions",
        ["organization_id", "applied"],
        unique=False,
    )

    op.create_table(
        "incident_classifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("issue_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("sub_category", sa.String(length=255), nullable=True),
        sa.Column("regulatory_implications", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("notification_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("auto_classified", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("classification_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("classified_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "category IN ('security_breach', 'privacy_violation', 'service_disruption', 'data_corruption', 'unauthorized_access', 'insider_threat', 'third_party_failure', 'regulatory_event')",
            name="ck_incident_classifications_category",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["issue_id"], ["issues.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["classification_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("issue_id", name="uq_incident_classifications_issue_id"),
    )
    op.create_index(
        "ix_incident_classifications_org_category",
        "incident_classifications",
        ["organization_id", "category"],
        unique=False,
    )
    op.create_index(
        "ix_incident_classifications_org_issue",
        "incident_classifications",
        ["organization_id", "issue_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_incident_classifications_org_issue", table_name="incident_classifications")
    op.drop_index("ix_incident_classifications_org_category", table_name="incident_classifications")
    op.drop_table("incident_classifications")

    op.drop_index("ix_remediation_suggestions_org_applied", table_name="remediation_suggestions")
    op.drop_index("ix_remediation_suggestions_org_issue", table_name="remediation_suggestions")
    op.drop_table("remediation_suggestions")
