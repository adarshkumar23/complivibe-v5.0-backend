"""risk register and link tables

Revision ID: 0010_risk_register_links
Revises: 0009_evidence_metadata_and_links
Create Date: 2026-06-18 13:05:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0010_risk_register_links"
down_revision: Union[str, Sequence[str], None] = "0009_evidence_metadata_and_links"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("risks", sa.Column("category", sa.String(length=32), nullable=False, server_default="other"))
    op.add_column("risks", sa.Column("severity", sa.String(length=16), nullable=False, server_default="low"))
    op.add_column("risks", sa.Column("inherent_score", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("risks", sa.Column("residual_likelihood", sa.Integer(), nullable=True))
    op.add_column("risks", sa.Column("residual_impact", sa.Integer(), nullable=True))
    op.add_column("risks", sa.Column("residual_score", sa.Integer(), nullable=True))
    op.add_column("risks", sa.Column("treatment_strategy", sa.String(length=32), nullable=False, server_default="undecided"))
    op.add_column("risks", sa.Column("target_date", sa.DateTime(timezone=True), nullable=True))
    op.add_column("risks", sa.Column("accepted_by_user_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("risks", sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("risks", sa.Column("acceptance_reason", sa.Text(), nullable=True))
    op.add_column("risks", sa.Column("review_due_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("risks", sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("risks", sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True))

    op.create_foreign_key(
        "fk_risks_accepted_by_user_id_users",
        "risks",
        "users",
        ["accepted_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_risks_created_by_user_id_users",
        "risks",
        "users",
        ["created_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_index("ix_risk_org_severity", "risks", ["organization_id", "severity"], unique=False)
    op.create_index("ix_risk_org_category", "risks", ["organization_id", "category"], unique=False)
    op.create_index("ix_risk_org_treatment", "risks", ["organization_id", "treatment_strategy"], unique=False)

    op.create_table(
        "risk_control_links",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("risk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("control_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("link_type", sa.String(length=32), nullable=False, server_default="mitigates"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("linked_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unlinked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["risk_id"], ["risks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["control_id"], ["controls.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["linked_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "risk_id", "control_id", name="uq_risk_control_link"),
    )
    op.create_index("ix_risk_control_links_risk_id", "risk_control_links", ["risk_id"], unique=False)
    op.create_index("ix_risk_control_links_control_id", "risk_control_links", ["control_id"], unique=False)
    op.create_index("ix_risk_control_links_status", "risk_control_links", ["status"], unique=False)

    op.create_table(
        "risk_evidence_links",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("risk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("link_type", sa.String(length=32), nullable=False, server_default="related"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("linked_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unlinked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["risk_id"], ["risks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evidence_item_id"], ["evidence_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["linked_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "risk_id", "evidence_item_id", name="uq_risk_evidence_link"),
    )
    op.create_index("ix_risk_evidence_links_risk_id", "risk_evidence_links", ["risk_id"], unique=False)
    op.create_index("ix_risk_evidence_links_evidence_id", "risk_evidence_links", ["evidence_item_id"], unique=False)
    op.create_index("ix_risk_evidence_links_status", "risk_evidence_links", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_risk_evidence_links_status", table_name="risk_evidence_links")
    op.drop_index("ix_risk_evidence_links_evidence_id", table_name="risk_evidence_links")
    op.drop_index("ix_risk_evidence_links_risk_id", table_name="risk_evidence_links")
    op.drop_table("risk_evidence_links")

    op.drop_index("ix_risk_control_links_status", table_name="risk_control_links")
    op.drop_index("ix_risk_control_links_control_id", table_name="risk_control_links")
    op.drop_index("ix_risk_control_links_risk_id", table_name="risk_control_links")
    op.drop_table("risk_control_links")

    op.drop_index("ix_risk_org_treatment", table_name="risks")
    op.drop_index("ix_risk_org_category", table_name="risks")
    op.drop_index("ix_risk_org_severity", table_name="risks")

    op.drop_constraint("fk_risks_created_by_user_id_users", "risks", type_="foreignkey")
    op.drop_constraint("fk_risks_accepted_by_user_id_users", "risks", type_="foreignkey")

    op.drop_column("risks", "created_by_user_id")
    op.drop_column("risks", "metadata_json")
    op.drop_column("risks", "review_due_at")
    op.drop_column("risks", "acceptance_reason")
    op.drop_column("risks", "accepted_at")
    op.drop_column("risks", "accepted_by_user_id")
    op.drop_column("risks", "target_date")
    op.drop_column("risks", "treatment_strategy")
    op.drop_column("risks", "residual_score")
    op.drop_column("risks", "residual_impact")
    op.drop_column("risks", "residual_likelihood")
    op.drop_column("risks", "inherent_score")
    op.drop_column("risks", "severity")
    op.drop_column("risks", "category")
