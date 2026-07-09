"""add many-to-many legal matter <-> evidence/control link tables

Revision ID: 0271_legal_matter_evidence_control_links
Revises: 0270_carbon_accounting_api_key
Create Date: 2026-07-08 00:00:00.000000

LegalMatter only ever had single-value related_risk_id/related_issue_id FKs -- there
was no way to link a matter to evidence or controls at all, and even the existing
risk/issue linking couldn't represent a matter referencing more than one of each,
which real-world legal matters routinely need. This adds proper many-to-many link
tables for legal matter <-> evidence and legal matter <-> control, following the
same active/status pattern already used by risk_control_links.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0278_legal_matter_evidence_control_links"
down_revision: str | None = "0277_carbon_accounting_api_key"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "legal_matter_evidence_links",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("matter_id", sa.Uuid(), sa.ForeignKey("legal_matters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("evidence_id", sa.Uuid(), sa.ForeignKey("evidence_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("linked_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unlinked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "matter_id", "evidence_id", name="uq_legal_matter_evidence_link"),
    )
    op.create_index("ix_legal_matter_evidence_links_matter_id", "legal_matter_evidence_links", ["matter_id"])
    op.create_index("ix_legal_matter_evidence_links_evidence_id", "legal_matter_evidence_links", ["evidence_id"])
    op.create_index("ix_legal_matter_evidence_links_status", "legal_matter_evidence_links", ["status"])

    op.create_table(
        "legal_matter_control_links",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("matter_id", sa.Uuid(), sa.ForeignKey("legal_matters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("control_id", sa.Uuid(), sa.ForeignKey("controls.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("linked_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unlinked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "matter_id", "control_id", name="uq_legal_matter_control_link"),
    )
    op.create_index("ix_legal_matter_control_links_matter_id", "legal_matter_control_links", ["matter_id"])
    op.create_index("ix_legal_matter_control_links_control_id", "legal_matter_control_links", ["control_id"])
    op.create_index("ix_legal_matter_control_links_status", "legal_matter_control_links", ["status"])


def downgrade() -> None:
    op.drop_index("ix_legal_matter_control_links_status", table_name="legal_matter_control_links")
    op.drop_index("ix_legal_matter_control_links_control_id", table_name="legal_matter_control_links")
    op.drop_index("ix_legal_matter_control_links_matter_id", table_name="legal_matter_control_links")
    op.drop_table("legal_matter_control_links")

    op.drop_index("ix_legal_matter_evidence_links_status", table_name="legal_matter_evidence_links")
    op.drop_index("ix_legal_matter_evidence_links_evidence_id", table_name="legal_matter_evidence_links")
    op.drop_index("ix_legal_matter_evidence_links_matter_id", table_name="legal_matter_evidence_links")
    op.drop_table("legal_matter_evidence_links")
