"""evidence metadata and control links

Revision ID: 0009_evidence_metadata_and_links
Revises: 0008_email_worker_orchestration
Create Date: 2026-06-18 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0009_evidence_metadata_and_links"
down_revision: Union[str, Sequence[str], None] = "0008_email_worker_orchestration"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("evidence_items", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("evidence_items", sa.Column("evidence_type", sa.String(length=64), nullable=False, server_default="other"))
    op.add_column("evidence_items", sa.Column("source", sa.String(length=32), nullable=False, server_default="manual"))
    op.add_column("evidence_items", sa.Column("status", sa.String(length=32), nullable=False, server_default="active"))
    op.add_column("evidence_items", sa.Column("review_status", sa.String(length=32), nullable=False, server_default="not_reviewed"))
    op.add_column("evidence_items", sa.Column("freshness_status", sa.String(length=32), nullable=False, server_default="unknown"))
    op.add_column("evidence_items", sa.Column("file_name", sa.String(length=255), nullable=True))
    op.add_column("evidence_items", sa.Column("mime_type", sa.String(length=255), nullable=True))
    op.add_column("evidence_items", sa.Column("size_bytes", sa.BigInteger(), nullable=True))
    op.add_column("evidence_items", sa.Column("checksum_sha256", sa.String(length=128), nullable=True))
    op.add_column("evidence_items", sa.Column("storage_provider", sa.String(length=120), nullable=True))
    op.add_column("evidence_items", sa.Column("storage_key", sa.String(length=512), nullable=True))
    op.add_column("evidence_items", sa.Column("external_reference_url", sa.String(length=1024), nullable=True))
    op.add_column("evidence_items", sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True))
    op.add_column("evidence_items", sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("evidence_items", sa.Column("collected_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("evidence_items", sa.Column("reviewed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("evidence_items", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("evidence_items", sa.Column("review_notes", sa.Text(), nullable=True))

    op.alter_column(
        "evidence_items",
        "metadata_json",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        nullable=True,
        existing_nullable=False,
    )

    op.create_foreign_key(
        "fk_evidence_items_reviewed_by_user_id_users",
        "evidence_items",
        "users",
        ["reviewed_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.drop_index("ix_evidence_org_control", table_name="evidence_items")
    op.create_index("ix_evidence_org_review_status", "evidence_items", ["organization_id", "review_status"], unique=False)
    op.create_index("ix_evidence_org_freshness_status", "evidence_items", ["organization_id", "freshness_status"], unique=False)
    op.create_index("ix_evidence_org_type", "evidence_items", ["organization_id", "evidence_type"], unique=False)
    op.create_index("ix_evidence_org_source", "evidence_items", ["organization_id", "source"], unique=False)

    op.create_table(
        "evidence_control_links",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("control_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("link_status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("confidence", sa.String(length=32), nullable=False, server_default="manual_confirmed"),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("linked_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unlinked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evidence_item_id"], ["evidence_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["control_id"], ["controls.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["linked_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "evidence_item_id", "control_id", name="uq_evidence_control_link"),
    )
    op.create_index("ix_evidence_control_links_control_id", "evidence_control_links", ["control_id"], unique=False)
    op.create_index("ix_evidence_control_links_evidence_id", "evidence_control_links", ["evidence_item_id"], unique=False)
    op.create_index("ix_evidence_control_links_status", "evidence_control_links", ["link_status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_evidence_control_links_status", table_name="evidence_control_links")
    op.drop_index("ix_evidence_control_links_evidence_id", table_name="evidence_control_links")
    op.drop_index("ix_evidence_control_links_control_id", table_name="evidence_control_links")
    op.drop_table("evidence_control_links")

    op.drop_index("ix_evidence_org_source", table_name="evidence_items")
    op.drop_index("ix_evidence_org_type", table_name="evidence_items")
    op.drop_index("ix_evidence_org_freshness_status", table_name="evidence_items")
    op.drop_index("ix_evidence_org_review_status", table_name="evidence_items")
    op.create_index("ix_evidence_org_control", "evidence_items", ["organization_id", "control_id"], unique=False)

    op.drop_constraint("fk_evidence_items_reviewed_by_user_id_users", "evidence_items", type_="foreignkey")

    op.alter_column(
        "evidence_items",
        "metadata_json",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        nullable=False,
        existing_nullable=True,
    )

    op.drop_column("evidence_items", "review_notes")
    op.drop_column("evidence_items", "reviewed_at")
    op.drop_column("evidence_items", "reviewed_by_user_id")
    op.drop_column("evidence_items", "collected_at")
    op.drop_column("evidence_items", "valid_until")
    op.drop_column("evidence_items", "valid_from")
    op.drop_column("evidence_items", "external_reference_url")
    op.drop_column("evidence_items", "storage_key")
    op.drop_column("evidence_items", "storage_provider")
    op.drop_column("evidence_items", "checksum_sha256")
    op.drop_column("evidence_items", "size_bytes")
    op.drop_column("evidence_items", "mime_type")
    op.drop_column("evidence_items", "file_name")
    op.drop_column("evidence_items", "freshness_status")
    op.drop_column("evidence_items", "review_status")
    op.drop_column("evidence_items", "status")
    op.drop_column("evidence_items", "source")
    op.drop_column("evidence_items", "evidence_type")
    op.drop_column("evidence_items", "description")
