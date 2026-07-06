"""add evidence automation rules for inbound connector

Revision ID: 0246_evidence_automation_i1
Revises: 0245_saml_replay
Create Date: 2026-07-06
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "0246_evidence_automation_i1"
down_revision: str | None = "0245_saml_replay"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evidence_automation_rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("trigger_source", sa.String(length=16), nullable=False),
        sa.Column("trigger_config", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("target_control_id", sa.Uuid(), nullable=True),
        sa.Column("evidence_type", sa.String(length=64), nullable=False, server_default=sa.text("'other'")),
        sa.Column("transform_template", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "trigger_source IN ('webhook','email','form')",
            name="ck_evidence_automation_rules_source",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_control_id"], ["controls.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_evidence_automation_rules_org_source",
        "evidence_automation_rules",
        ["organization_id", "trigger_source"],
        unique=False,
    )
    op.create_index(
        "ix_evidence_automation_rules_org_active",
        "evidence_automation_rules",
        ["organization_id", "is_active"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_evidence_automation_rules_org_active", table_name="evidence_automation_rules")
    op.drop_index("ix_evidence_automation_rules_org_source", table_name="evidence_automation_rules")
    op.drop_table("evidence_automation_rules")
