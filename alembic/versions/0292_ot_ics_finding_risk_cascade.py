"""OT/ICS finding + segment-concentration -> risk-register cascade

Revision ID: 0292_ot_ics_finding_risk_cascade
Revises: 0291_geopolitical_risk_vendor_cascade
Create Date: 2026-07-09 00:00:00.000000

Root-cause fix for G6 item 4: OT/ICS convergence-monitoring findings -- even
high/critical severity ones, and even flagged multi-finding network segments --
never created a risk-register entry, unlike every other domain's staleness/finding
logic in this codebase (vendor concentration risk, KYB/AML, geopolitical risk, ...).

Adds:
  - `ot_ics_findings.risk_id`: set once a high/critical finding creates a Risk, so
    the finding <-> risk link is directly auditable and idempotent per finding.
  - `ot_ics_segment_risk_detections`: one row per organization/network_segment,
    tracking the current open-high-or-critical concentration count and the Risk
    created once that segment first crosses the "flagged" threshold (mirrors
    `vendor_concentration_risk_detections`' create-once/keep-risk_id pattern).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0292_ot_ics_finding_risk_cascade"
down_revision: str | None = "0291_geopolitical_risk_vendor_cascade"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ot_ics_findings",
        sa.Column("risk_id", sa.Uuid(), sa.ForeignKey("risks.id", ondelete="SET NULL"), nullable=True),
    )

    op.create_table(
        "ot_ics_segment_risk_detections",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("network_segment", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="below_threshold"),
        sa.Column("open_high_or_critical_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("threshold_count", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("risk_id", sa.Uuid(), sa.ForeignKey("risks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_ot_ics_segment_risk_org_segment",
        "ot_ics_segment_risk_detections",
        ["organization_id", "network_segment"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_ot_ics_segment_risk_org_segment", table_name="ot_ics_segment_risk_detections")
    op.drop_table("ot_ics_segment_risk_detections")
    op.drop_column("ot_ics_findings", "risk_id")
