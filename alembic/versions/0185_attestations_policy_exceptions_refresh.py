"""refresh attestations and policy exceptions for sprint3

Revision ID: 0185_attestations_policy_exceptions_refresh
Revises: 0184_ai_gov_diagnostic_snapshots
Create Date: 2026-07-01 00:00:00.000000
"""

from collections.abc import Sequence
import hashlib

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0185_attestations_policy_exceptions_refresh"
down_revision: str | None = "0184_ai_gov_diagnostic_snapshots"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Evolve existing attestation campaigns table to capture immutable content snapshot.
    op.add_column("policy_attestation_campaigns", sa.Column("policy_version_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("policy_attestation_campaigns", sa.Column("title", sa.String(length=200), nullable=True))
    op.add_column("policy_attestation_campaigns", sa.Column("attestation_text_shown", sa.Text(), nullable=True))
    op.add_column("policy_attestation_campaigns", sa.Column("content_hash", sa.String(length=64), nullable=True))

    op.create_foreign_key(
        "fk_pat_camp_pol_ver_id",
        "policy_attestation_campaigns",
        "compliance_policy_versions",
        ["policy_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_pat_camp_org_due",
        "policy_attestation_campaigns",
        ["organization_id", "due_date"],
        unique=False,
    )

    # Backfill content fields from existing rows.
    default_hash = hashlib.sha256("".encode()).hexdigest()
    op.execute("""
        UPDATE policy_attestation_campaigns
        SET title = COALESCE(title, name)
    """)
    op.execute("""
        UPDATE policy_attestation_campaigns
        SET attestation_text_shown = COALESCE(attestation_text_shown, description, '')
    """)
    op.execute(
        sa.text(
            """
            UPDATE policy_attestation_campaigns
            SET content_hash = :default_hash
            WHERE content_hash IS NULL
            """
        ).bindparams(default_hash=default_hash)
    )

    # New per-user attestation records table for sprint3 lifecycle semantics.
    op.create_table(
        "policy_attestations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("attested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("declined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decline_reason", sa.Text(), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('pending', 'attested', 'declined')", name="ck_pol_att_status"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["campaign_id"], ["policy_attestation_campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_id", "user_id", name="uq_pol_att_campaign_user"),
    )
    op.create_index("ix_pol_att_org_campaign", "policy_attestations", ["organization_id", "campaign_id"], unique=False)
    op.create_index("ix_pol_att_org_user", "policy_attestations", ["organization_id", "user_id"], unique=False)
    op.create_index("ix_pol_att_org_status", "policy_attestations", ["organization_id", "status"], unique=False)

    # Evolve existing policy_exceptions table with sprint3 lifecycle fields.
    op.add_column("policy_exceptions", sa.Column("reason", sa.Text(), nullable=True))
    op.add_column("policy_exceptions", sa.Column("approved_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("policy_exceptions", sa.Column("rejected_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("policy_exceptions", sa.Column("compensating_measure_description", sa.Text(), nullable=True))
    op.add_column("policy_exceptions", sa.Column("expiry_date", sa.Date(), nullable=True))
    op.add_column("policy_exceptions", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("policy_exceptions", sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("policy_exceptions", sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True))

    op.create_foreign_key("fk_pol_exc_approved_by", "policy_exceptions", "users", ["approved_by"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_pol_exc_rejected_by", "policy_exceptions", "users", ["rejected_by"], ["id"], ondelete="SET NULL")
    op.create_check_constraint(
        "ck_pol_exc_appr_not_req",
        "policy_exceptions",
        "approved_by IS NULL OR approved_by <> requested_by",
    )
    op.create_index("ix_pol_exc_org_expiry", "policy_exceptions", ["organization_id", "expiry_date"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_pol_exc_org_expiry", table_name="policy_exceptions")
    op.drop_constraint("ck_pol_exc_appr_not_req", "policy_exceptions", type_="check")
    op.drop_constraint("fk_pol_exc_rejected_by", "policy_exceptions", type_="foreignkey")
    op.drop_constraint("fk_pol_exc_approved_by", "policy_exceptions", type_="foreignkey")

    op.drop_column("policy_exceptions", "expired_at")
    op.drop_column("policy_exceptions", "rejected_at")
    op.drop_column("policy_exceptions", "approved_at")
    op.drop_column("policy_exceptions", "expiry_date")
    op.drop_column("policy_exceptions", "compensating_measure_description")
    op.drop_column("policy_exceptions", "rejected_by")
    op.drop_column("policy_exceptions", "approved_by")
    op.drop_column("policy_exceptions", "reason")

    op.drop_index("ix_pol_att_org_status", table_name="policy_attestations")
    op.drop_index("ix_pol_att_org_user", table_name="policy_attestations")
    op.drop_index("ix_pol_att_org_campaign", table_name="policy_attestations")
    op.drop_table("policy_attestations")

    op.drop_index("ix_pat_camp_org_due", table_name="policy_attestation_campaigns")
    op.drop_constraint("fk_pat_camp_pol_ver_id", "policy_attestation_campaigns", type_="foreignkey")
    op.drop_column("policy_attestation_campaigns", "content_hash")
    op.drop_column("policy_attestation_campaigns", "attestation_text_shown")
    op.drop_column("policy_attestation_campaigns", "title")
    op.drop_column("policy_attestation_campaigns", "policy_version_id")
