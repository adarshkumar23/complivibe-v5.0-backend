"""ai system governance reviews and attestations

Revision ID: 0038_ai_system_governance_reviews_attestations
Revises: 0037_ai_system_manual_links
Create Date: 2026-06-19 13:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0038_ai_system_governance_reviews_attestations"
down_revision: str | None = "0037_ai_system_manual_links"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_system_governance_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ai_system_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("review_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("outcome", sa.String(length=64), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("checklist_json", sa.JSON(), nullable=True),
        sa.Column("findings_json", sa.JSON(), nullable=True),
        sa.Column("conditions_json", sa.JSON(), nullable=True),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("assigned_to_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("started_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column("caveat", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assigned_to_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["started_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["completed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["cancelled_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_system_governance_reviews_organization_id",
        "ai_system_governance_reviews",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_system_gov_reviews_org_ai_system",
        "ai_system_governance_reviews",
        ["organization_id", "ai_system_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_system_gov_reviews_org_status",
        "ai_system_governance_reviews",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_ai_system_gov_reviews_org_type",
        "ai_system_governance_reviews",
        ["organization_id", "review_type"],
        unique=False,
    )
    op.create_index(
        "ix_ai_system_gov_reviews_org_outcome",
        "ai_system_governance_reviews",
        ["organization_id", "outcome"],
        unique=False,
    )

    op.create_table(
        "ai_system_governance_attestations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ai_system_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("review_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("signer_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("signer_role_name", sa.String(length=64), nullable=True),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("checklist_snapshot_json", sa.JSON(), nullable=True),
        sa.Column("review_snapshot_json", sa.JSON(), nullable=True),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("signature_algorithm", sa.String(length=32), nullable=False),
        sa.Column("internal_signature", sa.String(length=128), nullable=False),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("caveat", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["review_id"], ["ai_system_governance_reviews.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["signer_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "review_id",
            "signer_user_id",
            name="uq_ai_system_gov_attestation_signer_per_review",
        ),
    )
    op.create_index(
        "ix_ai_system_governance_attestations_organization_id",
        "ai_system_governance_attestations",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_system_gov_attestations_org_ai_system",
        "ai_system_governance_attestations",
        ["organization_id", "ai_system_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_system_gov_attestations_org_review",
        "ai_system_governance_attestations",
        ["organization_id", "review_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_system_gov_attestations_org_signed_at",
        "ai_system_governance_attestations",
        ["organization_id", "signed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ai_system_gov_attestations_org_signed_at", table_name="ai_system_governance_attestations")
    op.drop_index("ix_ai_system_gov_attestations_org_review", table_name="ai_system_governance_attestations")
    op.drop_index("ix_ai_system_gov_attestations_org_ai_system", table_name="ai_system_governance_attestations")
    op.drop_index("ix_ai_system_governance_attestations_organization_id", table_name="ai_system_governance_attestations")
    op.drop_table("ai_system_governance_attestations")

    op.drop_index("ix_ai_system_gov_reviews_org_outcome", table_name="ai_system_governance_reviews")
    op.drop_index("ix_ai_system_gov_reviews_org_type", table_name="ai_system_governance_reviews")
    op.drop_index("ix_ai_system_gov_reviews_org_status", table_name="ai_system_governance_reviews")
    op.drop_index("ix_ai_system_gov_reviews_org_ai_system", table_name="ai_system_governance_reviews")
    op.drop_index("ix_ai_system_governance_reviews_organization_id", table_name="ai_system_governance_reviews")
    op.drop_table("ai_system_governance_reviews")
