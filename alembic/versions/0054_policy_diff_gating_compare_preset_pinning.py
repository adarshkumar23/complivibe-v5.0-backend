"""policy diff gating compare preset pinning

Revision ID: 0054_policy_diff_gating_compare_preset_pinning
Revises: 0053_policy_diff_gating_compare_preset_versions
Create Date: 2026-06-19 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0054_policy_diff_gating_compare_preset_pinning"
down_revision: str | None = "0053_policy_diff_gating_compare_preset_versions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ai_system_governance_policy_diff_gating_compare_presets",
        sa.Column("pinned_version_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "ai_system_governance_policy_diff_gating_compare_presets",
        sa.Column(
            "version_selection_mode",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'active_then_mutable'"),
        ),
    )
    op.add_column(
        "ai_system_governance_policy_diff_gating_compare_presets",
        sa.Column(
            "allow_explicit_version_override",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "ai_system_governance_policy_diff_gating_compare_presets",
        sa.Column("pinned_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "ai_system_governance_policy_diff_gating_compare_presets",
        sa.Column("pinned_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "ai_system_governance_policy_diff_gating_compare_presets",
        sa.Column("pin_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "ai_system_governance_policy_diff_gating_compare_presets",
        sa.Column("unpinned_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "ai_system_governance_policy_diff_gating_compare_presets",
        sa.Column("unpinned_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "ai_system_governance_policy_diff_gating_compare_presets",
        sa.Column("unpin_reason", sa.Text(), nullable=True),
    )

    op.create_foreign_key(
        "fk_ai_sys_gov_policy_diff_gating_cmp_presets_pinned_version_id",
        "ai_system_governance_policy_diff_gating_compare_presets",
        "ai_system_governance_policy_diff_gating_compare_preset_versions",
        ["pinned_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_ai_sys_gov_policy_diff_gating_cmp_presets_pinned_by_user_id",
        "ai_system_governance_policy_diff_gating_compare_presets",
        "users",
        ["pinned_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_ai_sys_gov_policy_diff_gating_cmp_presets_unpinned_by_user_id",
        "ai_system_governance_policy_diff_gating_compare_presets",
        "users",
        ["unpinned_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_ai_sys_gov_policy_diff_gating_cmp_preset_org_pinned_ver",
        "ai_system_governance_policy_diff_gating_compare_presets",
        ["organization_id", "pinned_version_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_sys_gov_policy_diff_gating_cmp_preset_org_pinned_ver",
        table_name="ai_system_governance_policy_diff_gating_compare_presets",
    )
    op.drop_constraint(
        "fk_ai_sys_gov_policy_diff_gating_cmp_presets_unpinned_by_user_id",
        "ai_system_governance_policy_diff_gating_compare_presets",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_ai_sys_gov_policy_diff_gating_cmp_presets_pinned_by_user_id",
        "ai_system_governance_policy_diff_gating_compare_presets",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_ai_sys_gov_policy_diff_gating_cmp_presets_pinned_version_id",
        "ai_system_governance_policy_diff_gating_compare_presets",
        type_="foreignkey",
    )
    op.drop_column("ai_system_governance_policy_diff_gating_compare_presets", "unpin_reason")
    op.drop_column("ai_system_governance_policy_diff_gating_compare_presets", "unpinned_by_user_id")
    op.drop_column("ai_system_governance_policy_diff_gating_compare_presets", "unpinned_at")
    op.drop_column("ai_system_governance_policy_diff_gating_compare_presets", "pin_reason")
    op.drop_column("ai_system_governance_policy_diff_gating_compare_presets", "pinned_by_user_id")
    op.drop_column("ai_system_governance_policy_diff_gating_compare_presets", "pinned_at")
    op.drop_column("ai_system_governance_policy_diff_gating_compare_presets", "allow_explicit_version_override")
    op.drop_column("ai_system_governance_policy_diff_gating_compare_presets", "version_selection_mode")
    op.drop_column("ai_system_governance_policy_diff_gating_compare_presets", "pinned_version_id")

