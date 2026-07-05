"""add pam session records

Revision ID: 0211_pam_session_records
Revises: 0210_non_human_identities
Create Date: 2026-07-05 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0211_pam_session_records"
down_revision: str | None = "0210_non_human_identities"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pam_session_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("external_session_id", sa.String(length=255), nullable=False),
        sa.Column("pam_provider", sa.String(length=120), nullable=True),
        sa.Column("identity", sa.String(length=255), nullable=False),
        sa.Column("privileged_account", sa.String(length=255), nullable=True),
        sa.Column("target_system", sa.String(length=255), nullable=False),
        sa.Column("target_resource_type", sa.String(length=120), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.String(length=255), nullable=True),
        sa.Column("approval_reference", sa.String(length=255), nullable=True),
        sa.Column("session_recording_url", sa.Text(), nullable=True),
        sa.Column("approval_status", sa.String(length=40), nullable=False),
        sa.Column("risk_status", sa.String(length=40), nullable=False),
        sa.Column("risk_reason", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("ingested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("flagged_by", sa.Uuid(), nullable=True),
        sa.Column("flagged_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["flagged_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pam_session_records_organization_id", "pam_session_records", ["organization_id"], unique=False)
    op.create_index("ix_pam_session_records_org_started", "pam_session_records", ["organization_id", "started_at"], unique=False)
    op.create_index("ix_pam_session_records_org_approval", "pam_session_records", ["organization_id", "approval_status"], unique=False)
    op.create_index("ix_pam_session_records_org_risk", "pam_session_records", ["organization_id", "risk_status"], unique=False)
    op.create_index("ix_pam_session_records_org_identity_target", "pam_session_records", ["organization_id", "identity", "target_system"], unique=False)
    op.create_index("uq_pam_session_records_org_external", "pam_session_records", ["organization_id", "external_session_id"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_pam_session_records_org_external", table_name="pam_session_records")
    op.drop_index("ix_pam_session_records_org_identity_target", table_name="pam_session_records")
    op.drop_index("ix_pam_session_records_org_risk", table_name="pam_session_records")
    op.drop_index("ix_pam_session_records_org_approval", table_name="pam_session_records")
    op.drop_index("ix_pam_session_records_org_started", table_name="pam_session_records")
    op.drop_index("ix_pam_session_records_organization_id", table_name="pam_session_records")
    op.drop_table("pam_session_records")
