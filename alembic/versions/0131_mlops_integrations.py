"""mlops integrations

Revision ID: 0131_mlops_integrations
Revises: 0130_ai_signals_recommendations
Create Date: 2026-06-25 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0131_mlops_integrations"
down_revision: str | None = "0130_ai_signals_recommendations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mlops_integrations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("integration_type", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("config_json", sa.Text(), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sync_status", sa.String(length=20), nullable=True),
        sa.Column("last_sync_error", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "integration_type IN ('mlflow', 'databricks', 'sagemaker', 'vertex_ai')",
            name="ck_mlops_integrations_type",
        ),
        sa.CheckConstraint(
            "sync_status IS NULL OR sync_status IN ('success', 'failed', 'in_progress')",
            name="ck_mlops_integrations_sync_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_mlops_integrations_org_type",
        "mlops_integrations",
        ["organization_id", "integration_type"],
        unique=False,
    )
    op.create_index(
        "ix_mlops_integrations_org_active",
        "mlops_integrations",
        ["organization_id", "is_active"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_mlops_integrations_org_active", table_name="mlops_integrations")
    op.drop_index("ix_mlops_integrations_org_type", table_name="mlops_integrations")
    op.drop_table("mlops_integrations")
