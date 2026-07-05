"""add rights_status and rights_expires_at to training_datasets

Revision ID: 0231_td_rights_lifecycle
Revises: 0230_vendor_remediation_portal
Create Date: 2026-07-05 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0231_td_rights_lifecycle"
down_revision: str | None = "0230_vendor_remediation_portal"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "training_datasets",
        sa.Column("rights_status", sa.String(length=20), nullable=False, server_default="active"),
    )
    op.add_column(
        "training_datasets",
        sa.Column("rights_expires_at", sa.Date(), nullable=True),
    )
    op.create_check_constraint(
        "ck_training_datasets_rights_status",
        "training_datasets",
        "rights_status IN ('active', 'expired', 'revoked')",
    )
    op.create_index(
        "ix_training_datasets_org_rights_status",
        "training_datasets",
        ["organization_id", "rights_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_training_datasets_org_rights_status", table_name="training_datasets")
    op.drop_constraint("ck_training_datasets_rights_status", "training_datasets", type_="check")
    op.drop_column("training_datasets", "rights_expires_at")
    op.drop_column("training_datasets", "rights_status")
