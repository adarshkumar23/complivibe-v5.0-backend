"""mlops deployment risk linkage

Revision ID: 0182_mlops_deployment_risk_linkage
Revises: 0181_mlops_adapter
Create Date: 2026-07-01 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "0182_mlops_deployment_risk_linkage"
down_revision: str | None = "0181_mlops_adapter"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "mlflow_model_registrations",
        sa.Column("auto_risk_created", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "mlflow_model_registrations",
        sa.Column("linked_risk_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_mf_reg_risk",
        "mlflow_model_registrations",
        "risks",
        ["linked_risk_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_mf_reg_risk", "mlflow_model_registrations", ["linked_risk_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_mf_reg_risk", table_name="mlflow_model_registrations")
    op.drop_constraint("fk_mf_reg_risk", "mlflow_model_registrations", type_="foreignkey")
    op.drop_column("mlflow_model_registrations", "linked_risk_id")
    op.drop_column("mlflow_model_registrations", "auto_risk_created")
