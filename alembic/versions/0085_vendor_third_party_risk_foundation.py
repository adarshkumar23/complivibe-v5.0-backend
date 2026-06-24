"""vendor third party risk foundation

Revision ID: 0085_vendor_third_party_risk_foundation
Revises: 0084_compliance_policy_control_links
Create Date: 2026-06-22 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0085_vendor_third_party_risk_foundation"
down_revision: str | None = "0084_compliance_policy_control_links"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "vendors",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("vendor_type", sa.String(length=64), nullable=False),
        sa.Column("website", sa.String(length=512), nullable=True),
        sa.Column("primary_contact_name", sa.String(length=255), nullable=True),
        sa.Column("primary_contact_email", sa.String(length=320), nullable=True),
        sa.Column("risk_tier", sa.String(length=32), nullable=False, server_default=sa.text("'not_assessed'")),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'active'")),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("data_access", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("processes_personal_data", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("sub_processor", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("tags_json", sa.JSON(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("archive_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["archived_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vendors_organization_id", "vendors", ["organization_id"], unique=False)
    op.create_index("ix_vendors_org_status", "vendors", ["organization_id", "status"], unique=False)
    op.create_index("ix_vendors_org_risk_tier", "vendors", ["organization_id", "risk_tier"], unique=False)
    op.create_index("ix_vendors_org_vendor_type", "vendors", ["organization_id", "vendor_type"], unique=False)
    op.create_index("ix_vendors_org_data_access", "vendors", ["organization_id", "data_access"], unique=False)
    op.create_index("ix_vendors_org_owner", "vendors", ["organization_id", "owner_user_id"], unique=False)
    op.create_index("ix_vendors_org_archived", "vendors", ["organization_id", "archived_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_vendors_org_archived", table_name="vendors")
    op.drop_index("ix_vendors_org_owner", table_name="vendors")
    op.drop_index("ix_vendors_org_data_access", table_name="vendors")
    op.drop_index("ix_vendors_org_vendor_type", table_name="vendors")
    op.drop_index("ix_vendors_org_risk_tier", table_name="vendors")
    op.drop_index("ix_vendors_org_status", table_name="vendors")
    op.drop_index("ix_vendors_organization_id", table_name="vendors")
    op.drop_table("vendors")
