"""employee attestations

Revision ID: 0099_employee_attestations
Revises: 0098_technical_control_tests
Create Date: 2026-06-24 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0099_employee_attestations"
down_revision: str | None = "0098_technical_control_tests"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "policy_attestation_campaigns",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_version", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("attestation_expiry_days", sa.Integer(), server_default=sa.text("365"), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'active'"), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('active', 'completed', 'cancelled')",
            name="ck_policy_attestation_campaigns_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["policy_id"], ["compliance_policies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_policy_attestation_campaigns_organization_id",
        "policy_attestation_campaigns",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_policy_attestation_campaigns_org_policy",
        "policy_attestation_campaigns",
        ["organization_id", "policy_id"],
        unique=False,
    )
    op.create_index(
        "ix_policy_attestation_campaigns_org_status",
        "policy_attestation_campaigns",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "uq_policy_attestation_campaigns_org_name_active",
        "policy_attestation_campaigns",
        ["organization_id", "name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "policy_attestation_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("attested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exemption_reason", sa.Text(), nullable=True),
        sa.Column("exempted_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reminder_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'attested', 'expired', 'exempted')",
            name="ck_policy_attestation_records_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["campaign_id"], ["policy_attestation_campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["exempted_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_id", "user_id", name="uq_policy_attestation_records_campaign_user"),
    )
    op.create_index(
        "ix_policy_attestation_records_organization_id",
        "policy_attestation_records",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_policy_attestation_records_org_campaign",
        "policy_attestation_records",
        ["organization_id", "campaign_id"],
        unique=False,
    )
    op.create_index(
        "ix_policy_attestation_records_org_user_status",
        "policy_attestation_records",
        ["organization_id", "user_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_policy_attestation_records_org_status_expires",
        "policy_attestation_records",
        ["organization_id", "status", "expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_policy_attestation_records_org_status_expires", table_name="policy_attestation_records")
    op.drop_index("ix_policy_attestation_records_org_user_status", table_name="policy_attestation_records")
    op.drop_index("ix_policy_attestation_records_org_campaign", table_name="policy_attestation_records")
    op.drop_index("ix_policy_attestation_records_organization_id", table_name="policy_attestation_records")
    op.drop_table("policy_attestation_records")

    op.drop_index("uq_policy_attestation_campaigns_org_name_active", table_name="policy_attestation_campaigns")
    op.drop_index("ix_policy_attestation_campaigns_org_status", table_name="policy_attestation_campaigns")
    op.drop_index("ix_policy_attestation_campaigns_org_policy", table_name="policy_attestation_campaigns")
    op.drop_index("ix_policy_attestation_campaigns_organization_id", table_name="policy_attestation_campaigns")
    op.drop_table("policy_attestation_campaigns")
