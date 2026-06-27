"""dsar automation and rights tracker

Revision ID: 0139_dsar_rights_tracker
Revises: 0138_privacy_ses_and_ropa
Create Date: 2026-06-26 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0139_dsar_rights_tracker"
down_revision: str | None = "0138_privacy_ses_and_ropa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "data_subject_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_ref", sa.String(length=50), nullable=False),
        sa.Column("request_type", sa.String(length=30), nullable=False),
        sa.Column("subject_name", sa.String(length=255), nullable=False),
        sa.Column("subject_email", sa.String(length=255), nullable=False),
        sa.Column("subject_identifier", sa.String(length=500), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default=sa.text("'received'")),
        sa.Column("regulatory_framework", sa.String(length=20), nullable=False, server_default=sa.text("'gdpr'")),
        sa.Column("response_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline_days", sa.Integer(), nullable=False, server_default=sa.text("30")),
        sa.Column("extension_granted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("extension_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("extension_reason", sa.Text(), nullable=True),
        sa.Column("identity_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("identity_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("identity_verified_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("assigned_handler_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("response_notes", sa.Text(), nullable=True),
        sa.Column("refusal_reason", sa.Text(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("fulfilled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "request_type IN ('access', 'erasure', 'portability', 'rectification', 'restriction', 'objection')",
            name="ck_data_subject_requests_request_type",
        ),
        sa.CheckConstraint(
            "status IN ('received', 'identity_verification', 'in_progress', 'on_hold', 'fulfilled', 'refused', 'partially_fulfilled', 'withdrawn')",
            name="ck_data_subject_requests_status",
        ),
        sa.CheckConstraint(
            "regulatory_framework IN ('gdpr', 'ccpa', 'dpdp', 'lgpd', 'custom')",
            name="ck_data_subject_requests_framework",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["identity_verified_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assigned_handler_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "request_ref", name="uq_data_subject_requests_org_ref"),
    )
    op.create_index("ix_data_subject_requests_org_status", "data_subject_requests", ["organization_id", "status"], unique=False)
    op.create_index("ix_data_subject_requests_org_type", "data_subject_requests", ["organization_id", "request_type"], unique=False)
    op.create_index("ix_data_subject_requests_org_deadline", "data_subject_requests", ["organization_id", "response_deadline"], unique=False)
    op.create_index("ix_data_subject_requests_org_subject_email", "data_subject_requests", ["organization_id", "subject_email"], unique=False)

    op.create_table(
        "dsr_fulfillment_steps",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("step_type", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("assigned_to", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "step_type IN ('identity_check', 'locate_data', 'review_data', 'prepare_response', 'legal_review', 'send_response', 'custom')",
            name="ck_dsr_fulfillment_steps_step_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'in_progress', 'completed', 'skipped')",
            name="ck_dsr_fulfillment_steps_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["request_id"], ["data_subject_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assigned_to"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_dsr_fulfillment_steps_request_order", "dsr_fulfillment_steps", ["request_id", "order_index"], unique=False)
    op.create_index("ix_dsr_fulfillment_steps_org_status", "dsr_fulfillment_steps", ["organization_id", "status"], unique=False)

    op.create_table(
        "dsr_sla_tracking",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("effective_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("response_breached", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("breach_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["request_id"], ["data_subject_requests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_id", name="uq_dsr_sla_tracking_request"),
    )
    op.create_index("ix_dsr_sla_tracking_org_deadline", "dsr_sla_tracking", ["organization_id", "effective_deadline"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_dsr_sla_tracking_org_deadline", table_name="dsr_sla_tracking")
    op.drop_table("dsr_sla_tracking")

    op.drop_index("ix_dsr_fulfillment_steps_org_status", table_name="dsr_fulfillment_steps")
    op.drop_index("ix_dsr_fulfillment_steps_request_order", table_name="dsr_fulfillment_steps")
    op.drop_table("dsr_fulfillment_steps")

    op.drop_index("ix_data_subject_requests_org_subject_email", table_name="data_subject_requests")
    op.drop_index("ix_data_subject_requests_org_deadline", table_name="data_subject_requests")
    op.drop_index("ix_data_subject_requests_org_type", table_name="data_subject_requests")
    op.drop_index("ix_data_subject_requests_org_status", table_name="data_subject_requests")
    op.drop_table("data_subject_requests")
