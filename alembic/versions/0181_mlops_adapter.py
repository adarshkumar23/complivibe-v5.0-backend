"""mlops adapter

Revision ID: 0181_mlops_adapter
Revises: 0180_ai_copilot_draft_mode
Create Date: 2026-07-01 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "0181_mlops_adapter"
down_revision: str | None = "0180_ai_copilot_draft_mode"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mlflow_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("connection_name", sa.String(length=150), nullable=False),
        sa.Column("ingest_token", sa.String(length=64), nullable=False),
        sa.Column("tracking_server_url", sa.String(length=500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE", name="fk_mf_conn_org"),
        sa.PrimaryKeyConstraint("id", name="pk_mf_conn"),
        sa.UniqueConstraint("organization_id", name="uq_mf_conn_org"),
        sa.UniqueConstraint("ingest_token", name="uq_mf_conn_token"),
    )
    op.create_index("ix_mf_conn_org_act", "mlflow_connections", ["organization_id", "is_active"], unique=False)

    op.create_table(
        "mlflow_model_registrations",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mlflow_connection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ai_system_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("model_version", sa.String(length=50), nullable=False),
        sa.Column("stage", sa.String(length=50), nullable=False),
        sa.Column("run_id", sa.String(length=100), nullable=True),
        sa.Column("metrics_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("tags_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("compliance_status", sa.String(length=50), nullable=False, server_default=sa.text("'pending_review'")),
        sa.Column("auto_linked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE", name="fk_mf_reg_org"),
        sa.ForeignKeyConstraint(["mlflow_connection_id"], ["mlflow_connections.id"], ondelete="CASCADE", name="fk_mf_reg_conn"),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"], ondelete="SET NULL", name="fk_mf_reg_ai"),
        sa.PrimaryKeyConstraint("id", name="pk_mf_reg"),
    )
    op.create_index("ix_mf_reg_org_model", "mlflow_model_registrations", ["organization_id", "model_name"], unique=False)
    op.create_index("ix_mf_reg_org_comp", "mlflow_model_registrations", ["organization_id", "compliance_status"], unique=False)
    op.create_index("ix_mf_reg_ai_sys", "mlflow_model_registrations", ["ai_system_id"], unique=False)
    op.create_index("ix_mf_reg_conn", "mlflow_model_registrations", ["mlflow_connection_id"], unique=False)

    op.create_table(
        "mlflow_drift_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mlflow_connection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ai_system_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("mlflow_model_registration_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("model_version", sa.String(length=50), nullable=True),
        sa.Column("drift_metric", sa.String(length=150), nullable=False),
        sa.Column("drift_value", sa.Numeric(precision=10, scale=6), nullable=False),
        sa.Column("drift_threshold", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("drift_context_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("auto_risk_created", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("linked_risk_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE", name="fk_mf_drift_org"),
        sa.ForeignKeyConstraint(["mlflow_connection_id"], ["mlflow_connections.id"], ondelete="CASCADE", name="fk_mf_drift_conn"),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"], ondelete="SET NULL", name="fk_mf_drift_ai"),
        sa.ForeignKeyConstraint(["mlflow_model_registration_id"], ["mlflow_model_registrations.id"], ondelete="SET NULL", name="fk_mf_drift_reg"),
        sa.ForeignKeyConstraint(["linked_risk_id"], ["risks.id"], ondelete="SET NULL", name="fk_mf_drift_risk"),
        sa.PrimaryKeyConstraint("id", name="pk_mf_drift"),
    )
    op.create_index("ix_mf_drift_org_sev", "mlflow_drift_events", ["organization_id", "severity"], unique=False)
    op.create_index("ix_mf_drift_org_model", "mlflow_drift_events", ["organization_id", "model_name"], unique=False)
    op.create_index("ix_mf_drift_ai_sys", "mlflow_drift_events", ["ai_system_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_mf_drift_ai_sys", table_name="mlflow_drift_events")
    op.drop_index("ix_mf_drift_org_model", table_name="mlflow_drift_events")
    op.drop_index("ix_mf_drift_org_sev", table_name="mlflow_drift_events")
    op.drop_table("mlflow_drift_events")

    op.drop_index("ix_mf_reg_conn", table_name="mlflow_model_registrations")
    op.drop_index("ix_mf_reg_ai_sys", table_name="mlflow_model_registrations")
    op.drop_index("ix_mf_reg_org_comp", table_name="mlflow_model_registrations")
    op.drop_index("ix_mf_reg_org_model", table_name="mlflow_model_registrations")
    op.drop_table("mlflow_model_registrations")

    op.drop_index("ix_mf_conn_org_act", table_name="mlflow_connections")
    op.drop_table("mlflow_connections")
