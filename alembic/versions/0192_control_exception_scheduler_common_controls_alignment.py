"""control exception scheduler and common-controls fields alignment

Revision ID: 0192_control_exception_scheduler_common_controls_alignment
Revises: 0191_customer_commitment_incident_trigger_type
Create Date: 2026-07-02 00:00:00.000000
"""

from collections.abc import Sequence
import re

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0192_control_exception_scheduler_common_controls_alignment"
down_revision: str | None = "0191_customer_commitment_incident_trigger_type"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:100] if slug else "common-control"


def upgrade() -> None:
    op.add_column(
        "controls",
        sa.Column("is_common_control", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("controls", sa.Column("common_control_tag", sa.String(length=100), nullable=True))

    bind = op.get_bind()
    controls = sa.table(
        "controls",
        sa.column("id", sa.Uuid()),
        sa.column("organization_id", sa.Uuid()),
        sa.column("title", sa.String()),
        sa.column("is_common_control", sa.Boolean()),
        sa.column("common_control_tag", sa.String()),
    )
    mappings = sa.table(
        "common_control_mappings",
        sa.column("organization_id", sa.Uuid()),
        sa.column("control_id", sa.Uuid()),
        sa.column("framework_id", sa.Uuid()),
    )
    frameworks = sa.table(
        "frameworks",
        sa.column("id", sa.Uuid()),
        sa.column("code", sa.String()),
    )

    has_mapping = (
        sa.select(sa.literal(1))
        .select_from(mappings)
        .where(
            mappings.c.organization_id == controls.c.organization_id,
            mappings.c.control_id == controls.c.id,
        )
        .limit(1)
    )

    bind.execute(
        sa.update(controls)
        .where(sa.exists(has_mapping))
        .values(is_common_control=True)
    )

    first_framework_code = (
        sa.select(frameworks.c.code)
        .select_from(
            mappings.join(frameworks, frameworks.c.id == mappings.c.framework_id),
        )
        .where(
            mappings.c.organization_id == controls.c.organization_id,
            mappings.c.control_id == controls.c.id,
        )
        .order_by(frameworks.c.code.asc())
        .limit(1)
        .scalar_subquery()
    )

    bind.execute(
        sa.update(controls)
        .where(
            controls.c.is_common_control.is_(True),
            controls.c.common_control_tag.is_(None),
        )
        .values(common_control_tag=first_framework_code)
    )

    # Fallback for mapped controls without a framework code.
    fallback_rows = bind.execute(
        sa.select(controls.c.id, controls.c.title).where(
            controls.c.is_common_control.is_(True),
            controls.c.common_control_tag.is_(None),
        )
    ).all()
    for row_id, title in fallback_rows:
        bind.execute(
            sa.update(controls)
            .where(controls.c.id == row_id)
            .values(common_control_tag=_slugify(title or "")),
        )


def downgrade() -> None:
    op.drop_column("controls", "common_control_tag")
    op.drop_column("controls", "is_common_control")
