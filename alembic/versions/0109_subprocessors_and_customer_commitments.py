"""subprocessor management and customer commitments

Revision ID: 0109_subprocessors_and_customer_commitments
Revises: 0108_inbound_questionnaire_engine
Create Date: 2026-06-24 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0109_subprocessors_and_customer_commitments"
down_revision: str | None = "0108_inbound_questionnaire_engine"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "subprocessors",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("service_description", sa.Text(), nullable=False),
        sa.Column("data_types_processed", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("legal_basis", sa.String(length=100), nullable=False),
        sa.Column("geographic_locations", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("data_transfer_mechanism", sa.String(length=100), nullable=True),
        sa.Column("dpa_status", sa.String(length=50), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("dpa_signed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dpa_expiry_date", sa.Date(), nullable=True),
        sa.Column("dpa_document_ref", sa.String(length=500), nullable=True),
        sa.Column("controller_type", sa.String(length=50), nullable=False),
        sa.Column("risk_level", sa.String(length=20), nullable=False, server_default=sa.text("'medium'")),
        sa.Column("status", sa.String(length=50), nullable=False, server_default=sa.text("'active'")),
        sa.Column("contact_name", sa.String(length=255), nullable=True),
        sa.Column("contact_email", sa.String(length=255), nullable=True),
        sa.Column("review_due_date", sa.Date(), nullable=True),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "legal_basis IN ('contract', 'legitimate_interest', 'consent', 'legal_obligation', 'vital_interests', 'public_task')",
            name="ck_subprocessors_legal_basis",
        ),
        sa.CheckConstraint(
            "data_transfer_mechanism IN ('sccs', 'adequacy_decision', 'bcrs', 'derogation', 'not_applicable') OR data_transfer_mechanism IS NULL",
            name="ck_subprocessors_data_transfer_mechanism",
        ),
        sa.CheckConstraint(
            "dpa_status IN ('pending', 'signed', 'not_required', 'expired', 'under_review')",
            name="ck_subprocessors_dpa_status",
        ),
        sa.CheckConstraint(
            "controller_type IN ('processor', 'sub_processor', 'joint_controller')",
            name="ck_subprocessors_controller_type",
        ),
        sa.CheckConstraint(
            "risk_level IN ('low', 'medium', 'high', 'critical')",
            name="ck_subprocessors_risk_level",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'inactive', 'under_review', 'offboarded')",
            name="ck_subprocessors_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["last_reviewed_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_subprocessors_org_status", "subprocessors", ["organization_id", "status"], unique=False)
    op.create_index("ix_subprocessors_org_dpa_status", "subprocessors", ["organization_id", "dpa_status"], unique=False)
    op.create_index("ix_subprocessors_org_risk_level", "subprocessors", ["organization_id", "risk_level"], unique=False)
    op.create_index("ix_subprocessors_dpa_expiry_status", "subprocessors", ["dpa_expiry_date", "dpa_status"], unique=False)

    op.create_table(
        "subprocessor_data_transfers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subprocessor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("origin_country", sa.String(length=2), nullable=False),
        sa.Column("destination_country", sa.String(length=2), nullable=False),
        sa.Column("data_categories", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("transfer_mechanism", sa.String(length=100), nullable=False),
        sa.Column("legal_basis", sa.String(length=100), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subprocessor_id"], ["subprocessors.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_subprocessor_data_transfers_subprocessor_id", "subprocessor_data_transfers", ["subprocessor_id"], unique=False)
    op.create_index(
        "ix_subprocessor_data_transfers_org_destination",
        "subprocessor_data_transfers",
        ["organization_id", "destination_country"],
        unique=False,
    )

    op.create_table(
        "customer_commitments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_name", sa.String(length=255), nullable=False),
        sa.Column("customer_email", sa.String(length=255), nullable=True),
        sa.Column("commitment_type", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("trigger_condition", sa.Text(), nullable=False),
        sa.Column("trigger_date", sa.Date(), nullable=True),
        sa.Column("notification_days_before", sa.Integer(), nullable=False, server_default=sa.text("7")),
        sa.Column("sla_hours", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default=sa.text("'active'")),
        sa.Column("linked_contract_ref", sa.String(length=500), nullable=True),
        sa.Column("assigned_owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fulfilled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fulfilled_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("fulfillment_notes", sa.Text(), nullable=True),
        sa.Column("waived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("waived_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("waiver_reason", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "commitment_type IN ('breach_notification', 'subprocessor_notice', 'audit_right', 'data_deletion', 'data_portability', 'sla', 'security_assessment', 'custom')",
            name="ck_customer_commitments_commitment_type",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'triggered', 'fulfilled', 'overdue', 'waived', 'expired')",
            name="ck_customer_commitments_status",
        ),
        sa.CheckConstraint(
            "notification_days_before >= 1 AND notification_days_before <= 90",
            name="ck_customer_commitments_notification_days_before",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assigned_owner_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["fulfilled_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["waived_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_customer_commitments_org_status", "customer_commitments", ["organization_id", "status"], unique=False)
    op.create_index(
        "ix_customer_commitments_org_type",
        "customer_commitments",
        ["organization_id", "commitment_type"],
        unique=False,
    )
    op.create_index("ix_customer_commitments_trigger_date_status", "customer_commitments", ["trigger_date", "status"], unique=False)
    op.create_index(
        "ix_customer_commitments_org_owner",
        "customer_commitments",
        ["organization_id", "assigned_owner_id"],
        unique=False,
    )

    op.create_table(
        "commitment_notification_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("commitment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("notification_type", sa.String(length=50), nullable=False),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("recipient_user_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("message_preview", sa.Text(), nullable=True),
        sa.Column("triggered_by", sa.String(length=50), nullable=False),
        sa.CheckConstraint(
            "notification_type IN ('reminder', 'triggered', 'escalation', 'fulfilled')",
            name="ck_commitment_notification_log_notification_type",
        ),
        sa.CheckConstraint(
            "triggered_by IN ('scheduler', 'manual', 'api')",
            name="ck_commitment_notification_log_triggered_by",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["commitment_id"], ["customer_commitments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_commitment_notification_log_commitment_id", "commitment_notification_log", ["commitment_id"], unique=False)
    op.create_index(
        "ix_commitment_notification_log_org_queued_at",
        "commitment_notification_log",
        ["organization_id", "queued_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_commitment_notification_log_org_queued_at", table_name="commitment_notification_log")
    op.drop_index("ix_commitment_notification_log_commitment_id", table_name="commitment_notification_log")
    op.drop_table("commitment_notification_log")

    op.drop_index("ix_customer_commitments_org_owner", table_name="customer_commitments")
    op.drop_index("ix_customer_commitments_trigger_date_status", table_name="customer_commitments")
    op.drop_index("ix_customer_commitments_org_type", table_name="customer_commitments")
    op.drop_index("ix_customer_commitments_org_status", table_name="customer_commitments")
    op.drop_table("customer_commitments")

    op.drop_index("ix_subprocessor_data_transfers_org_destination", table_name="subprocessor_data_transfers")
    op.drop_index("ix_subprocessor_data_transfers_subprocessor_id", table_name="subprocessor_data_transfers")
    op.drop_table("subprocessor_data_transfers")

    op.drop_index("ix_subprocessors_dpa_expiry_status", table_name="subprocessors")
    op.drop_index("ix_subprocessors_org_risk_level", table_name="subprocessors")
    op.drop_index("ix_subprocessors_org_dpa_status", table_name="subprocessors")
    op.drop_index("ix_subprocessors_org_status", table_name="subprocessors")
    op.drop_table("subprocessors")
