"""ai governance inventory shadow ai and use cases

Revision ID: 0123_ai_governance_inventory_shadow_usecases
Revises: 0122_add_pgvector_extension
Create Date: 2026-06-25 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

try:
    from pgvector.sqlalchemy import Vector
except Exception:  # pragma: no cover - migration fallback when pgvector package unavailable
    def Vector(dim: int):  # type: ignore[no-redef]
        _ = dim
        return sa.Text()

# revision identifiers, used by Alembic.
revision: str = "0123_ai_governance_inventory_shadow_usecases"
down_revision: str | None = "0122_add_pgvector_extension"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_governance_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ai_system_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_type", sa.String(length=20), nullable=False, server_default=sa.text("'user'")),
        sa.Column("event_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("actor_type IN ('user', 'scheduler', 'system')", name="ck_ai_governance_events_actor_type"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_governance_events_org_event_created",
        "ai_governance_events",
        ["organization_id", "event_type", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_ai_governance_events_org_system_created",
        "ai_governance_events",
        ["organization_id", "ai_system_id", "created_at"],
        unique=False,
    )
    op.create_index("ix_ai_governance_events_created", "ai_governance_events", ["created_at"], unique=False)

    op.add_column("ai_systems", sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("ai_systems", sa.Column("vendor_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column(
        "ai_systems",
        sa.Column("deployment_status", sa.String(length=50), nullable=False, server_default=sa.text("'development'")),
    )
    op.add_column("ai_systems", sa.Column("risk_tier", sa.String(length=20), nullable=True))
    op.add_column("ai_systems", sa.Column("data_sources_description", sa.Text(), nullable=True))
    op.add_column("ai_systems", sa.Column("purpose", sa.Text(), nullable=True))
    op.add_column("ai_systems", sa.Column("affected_population", sa.Text(), nullable=True))
    op.add_column("ai_systems", sa.Column("geographic_scope", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("ai_systems", sa.Column("description_embedding", Vector(384), nullable=True))
    op.add_column("ai_systems", sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("ai_systems", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key("fk_ai_systems_owner_id_users", "ai_systems", "users", ["owner_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_ai_systems_created_by_users", "ai_systems", "users", ["created_by"], ["id"], ondelete="SET NULL")
    op.create_index("ix_ai_systems_org_deployment_status", "ai_systems", ["organization_id", "deployment_status"], unique=False)
    op.create_index("ix_ai_systems_org_risk_tier", "ai_systems", ["organization_id", "risk_tier"], unique=False)

    op.create_table(
        "shadow_ai_detections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("detected_name", sa.String(length=255), nullable=False),
        sa.Column("detection_method", sa.String(length=50), nullable=False),
        sa.Column("confidence", sa.String(length=20), nullable=False, server_default=sa.text("'medium'")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'new'")),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("registered_system_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reported_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "detection_method IN ('questionnaire', 'manual_report', 'integration_analysis', 'network_scan')",
            name="ck_shadow_ai_detections_detection_method",
        ),
        sa.CheckConstraint("confidence IN ('high', 'medium', 'low')", name="ck_shadow_ai_detections_confidence"),
        sa.CheckConstraint(
            "status IN ('new', 'under_review', 'registered', 'dismissed')",
            name="ck_shadow_ai_detections_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reported_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["registered_system_id"], ["ai_systems.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_shadow_ai_detections_org_status", "shadow_ai_detections", ["organization_id", "status"], unique=False)
    op.create_index(
        "ix_shadow_ai_detections_org_detected_name",
        "shadow_ai_detections",
        ["organization_id", "detected_name"],
        unique=False,
    )

    op.create_table(
        "ai_use_cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ai_system_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("business_owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("use_case_type", sa.String(length=50), nullable=False),
        sa.Column("is_high_stakes", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("affected_groups", sa.Text(), nullable=True),
        sa.Column("deployment_context", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "use_case_type IN ('decision_making', 'classification', 'generation', 'recommendation', 'monitoring', 'automation', 'other')",
            name="ck_ai_use_cases_use_case_type",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["business_owner_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_use_cases_org_system", "ai_use_cases", ["organization_id", "ai_system_id"], unique=False)
    op.create_index("ix_ai_use_cases_org_high_stakes", "ai_use_cases", ["organization_id", "is_high_stakes"], unique=False)
    op.create_index("ix_ai_use_cases_org_type", "ai_use_cases", ["organization_id", "use_case_type"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_ai_use_cases_org_type", table_name="ai_use_cases")
    op.drop_index("ix_ai_use_cases_org_high_stakes", table_name="ai_use_cases")
    op.drop_index("ix_ai_use_cases_org_system", table_name="ai_use_cases")
    op.drop_table("ai_use_cases")

    op.drop_index("ix_shadow_ai_detections_org_detected_name", table_name="shadow_ai_detections")
    op.drop_index("ix_shadow_ai_detections_org_status", table_name="shadow_ai_detections")
    op.drop_table("shadow_ai_detections")

    op.drop_index("ix_ai_systems_org_risk_tier", table_name="ai_systems")
    op.drop_index("ix_ai_systems_org_deployment_status", table_name="ai_systems")
    op.drop_constraint("fk_ai_systems_created_by_users", "ai_systems", type_="foreignkey")
    op.drop_constraint("fk_ai_systems_owner_id_users", "ai_systems", type_="foreignkey")
    op.drop_column("ai_systems", "deleted_at")
    op.drop_column("ai_systems", "created_by")
    op.drop_column("ai_systems", "description_embedding")
    op.drop_column("ai_systems", "geographic_scope")
    op.drop_column("ai_systems", "affected_population")
    op.drop_column("ai_systems", "purpose")
    op.drop_column("ai_systems", "data_sources_description")
    op.drop_column("ai_systems", "risk_tier")
    op.drop_column("ai_systems", "deployment_status")
    op.drop_column("ai_systems", "vendor_id")
    op.drop_column("ai_systems", "owner_id")

    op.drop_index("ix_ai_governance_events_created", table_name="ai_governance_events")
    op.drop_index("ix_ai_governance_events_org_system_created", table_name="ai_governance_events")
    op.drop_index("ix_ai_governance_events_org_event_created", table_name="ai_governance_events")
    op.drop_table("ai_governance_events")
