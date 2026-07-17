"""add evidence_ai_assessments + evidence_ai_assessment_candidates (evidence AI-assist)

Evidence-vault AI-assist: after a document is uploaded (EVIDENCE_UPLOADED), an
async step ASSESSES it (never certifies it) and records a suggestion with
reasoning. Mirrors the Phase 3 compound-insight isolation shape exactly:
``evidence_ai_assessment_candidates`` is the flush-only flag queue the event bus
writes into; ``evidence_ai_assessments`` is the persisted, org-scoped output the
APScheduler drain writes (extraction + AI happen OUTSIDE the publisher's
transaction). These two tables are the ONLY tables this feature ever writes to.

organization_id is strictly non-nullable on both (tenant scoping, ADR-002).

Revision ID: 0308_evidence_ai_assessments
Revises: 0307_cm_kri_appetite_write
Create Date: 2026-07-17 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0308_evidence_ai_assessments"
down_revision: str | None = "0307_cm_kri_appetite_write"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evidence_ai_assessments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_item_id", sa.Uuid(), nullable=False),
        sa.Column("ai_assessment_status", sa.String(length=32), nullable=False),
        sa.Column("appears_to_be", sa.Text(), nullable=True),
        sa.Column("appears_to_cover", sa.Text(), nullable=True),
        sa.Column(
            "missing_or_mismatched_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("linked_control_id", sa.Uuid(), nullable=True),
        sa.Column("content_source", sa.String(length=32), nullable=False, server_default="none"),
        sa.Column("extracted_text_chars", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("provider_used", sa.String(length=20), nullable=True),
        sa.Column("used_byo_credentials", sa.Boolean(), nullable=True),
        sa.Column("assessment_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evidence_item_id"], ["evidence_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "ai_assessment_status IN ('suggested_valid', 'suggested_incomplete', "
            "'suggested_mismatch', 'unable_to_assess')",
            name="ck_evidence_ai_assessments_status",
        ),
    )
    op.create_index(
        "ix_evidence_ai_assessments_org_evidence",
        "evidence_ai_assessments",
        ["organization_id", "evidence_item_id", "created_at"],
    )

    op.create_table(
        "evidence_ai_assessment_candidates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_item_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=120), nullable=True),
        sa.Column("flagged_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_evidence_ai_assessment_candidates_pending",
        "evidence_ai_assessment_candidates",
        ["organization_id", "processed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_evidence_ai_assessment_candidates_pending", table_name="evidence_ai_assessment_candidates")
    op.drop_table("evidence_ai_assessment_candidates")
    op.drop_index("ix_evidence_ai_assessments_org_evidence", table_name="evidence_ai_assessments")
    op.drop_table("evidence_ai_assessments")
