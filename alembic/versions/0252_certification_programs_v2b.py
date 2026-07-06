"""add certification programs and activations

Revision ID: 0252_certification_programs_v2b
Revises: 0251_usage_based_pricing_p3b
Create Date: 2026-07-06 10:38:49.474972
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "0252_certification_programs_v2b"
down_revision: str | None = "0251_usage_based_pricing_p3b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "certification_programs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("target_framework", sa.String(length=64), nullable=False),
        sa.Column("duration_weeks", sa.Integer(), nullable=False),
        sa.Column(
            "weeks_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "prerequisites_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "evidence_templates_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_certification_program_name"),
        sa.CheckConstraint("duration_weeks > 0", name="ck_certification_program_duration_weeks"),
    )
    op.create_index("ix_certification_programs_name", "certification_programs", ["name"], unique=False)
    op.create_index(
        "ix_certification_programs_target_framework",
        "certification_programs",
        ["target_framework"],
        unique=False,
    )
    op.create_index("ix_certification_programs_status", "certification_programs", ["status"], unique=False)

    op.create_table(
        "certification_program_activations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("certification_program_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="active"),
        sa.Column("activated_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("projected_completion_date", sa.Date(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "metadata_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["certification_program_id"], ["certification_programs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["activated_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "certification_program_id",
            name="uq_cert_prog_activation_org_program",
        ),
    )
    op.create_index(
        "ix_cert_prog_activation_org_status",
        "certification_program_activations",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_cert_prog_activation_org_projected",
        "certification_program_activations",
        ["organization_id", "projected_completion_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_cert_prog_activation_org_projected", table_name="certification_program_activations")
    op.drop_index("ix_cert_prog_activation_org_status", table_name="certification_program_activations")
    op.drop_table("certification_program_activations")

    op.drop_index("ix_certification_programs_status", table_name="certification_programs")
    op.drop_index("ix_certification_programs_target_framework", table_name="certification_programs")
    op.drop_index("ix_certification_programs_name", table_name="certification_programs")
    op.drop_table("certification_programs")
