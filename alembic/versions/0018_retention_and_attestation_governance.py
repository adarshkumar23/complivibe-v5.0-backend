"""retention and attestation governance

Revision ID: 0018_retention_and_attestation_governance
Revises: 0017_export_jobs_foundation
Create Date: 2026-06-19 00:20:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0018_retention_and_attestation_governance"
down_revision: Union[str, Sequence[str], None] = "0017_export_jobs_foundation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "retention_policies",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("retention_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lock_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("legal_hold_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_retention_policies_org_entity", "retention_policies", ["organization_id", "entity_type"], unique=False)
    op.create_index("ix_retention_policies_org_status", "retention_policies", ["organization_id", "status"], unique=False)

    op.create_table(
        "export_attestations",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("export_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attestation_type", sa.String(length=64), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("attested_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.Text(), nullable=True),
        sa.Column("export_checksum_sha256", sa.String(length=128), nullable=False),
        sa.Column("export_integrity_signature", sa.String(length=256), nullable=True),
        sa.Column("attestation_checksum_sha256", sa.String(length=128), nullable=False),
        sa.Column("attestation_signature", sa.String(length=256), nullable=True),
        sa.Column("signing_key_id", sa.String(length=64), nullable=True),
        sa.Column("signature_algorithm", sa.String(length=64), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["export_job_id"], ["export_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["attested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["revoked_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_export_attestations_org_export", "export_attestations", ["organization_id", "export_job_id"], unique=False)
    op.create_index("ix_export_attestations_org_status", "export_attestations", ["organization_id", "status"], unique=False)
    op.create_index("ix_export_attestations_export_attested", "export_attestations", ["export_job_id", "attested_at"], unique=False)

    op.add_column("export_jobs", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("export_jobs", sa.Column("retention_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("export_jobs", sa.Column("legal_hold", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("export_jobs", sa.Column("legal_hold_reason", sa.Text(), nullable=True))
    op.add_column("export_jobs", sa.Column("legal_hold_set_by_user_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("export_jobs", sa.Column("legal_hold_set_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("export_jobs", sa.Column("attestation_status", sa.String(length=32), nullable=False, server_default="unattested"))
    op.add_column("export_jobs", sa.Column("latest_attestation_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_export_jobs_legal_hold_set_by_user_id",
        "export_jobs",
        "users",
        ["legal_hold_set_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_export_jobs_latest_attestation_id",
        "export_jobs",
        "export_attestations",
        ["latest_attestation_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_export_jobs_org_locked_until", "export_jobs", ["organization_id", "locked_until"], unique=False)
    op.create_index("ix_export_jobs_org_retention_until", "export_jobs", ["organization_id", "retention_until"], unique=False)
    op.create_index("ix_export_jobs_org_legal_hold", "export_jobs", ["organization_id", "legal_hold"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_export_jobs_org_legal_hold", table_name="export_jobs")
    op.drop_index("ix_export_jobs_org_retention_until", table_name="export_jobs")
    op.drop_index("ix_export_jobs_org_locked_until", table_name="export_jobs")
    op.drop_constraint("fk_export_jobs_latest_attestation_id", "export_jobs", type_="foreignkey")
    op.drop_constraint("fk_export_jobs_legal_hold_set_by_user_id", "export_jobs", type_="foreignkey")
    op.drop_column("export_jobs", "latest_attestation_id")
    op.drop_column("export_jobs", "attestation_status")
    op.drop_column("export_jobs", "legal_hold_set_at")
    op.drop_column("export_jobs", "legal_hold_set_by_user_id")
    op.drop_column("export_jobs", "legal_hold_reason")
    op.drop_column("export_jobs", "legal_hold")
    op.drop_column("export_jobs", "retention_until")
    op.drop_column("export_jobs", "locked_until")

    op.drop_index("ix_export_attestations_export_attested", table_name="export_attestations")
    op.drop_index("ix_export_attestations_org_status", table_name="export_attestations")
    op.drop_index("ix_export_attestations_org_export", table_name="export_attestations")
    op.drop_table("export_attestations")

    op.drop_index("ix_retention_policies_org_status", table_name="retention_policies")
    op.drop_index("ix_retention_policies_org_entity", table_name="retention_policies")
    op.drop_table("retention_policies")
