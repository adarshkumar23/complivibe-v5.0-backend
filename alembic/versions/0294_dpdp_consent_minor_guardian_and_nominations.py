"""add DPDP minor/guardian consent fields and data_principal_nominations table

Revision ID: 0294_dpdp_consent_minor_guardian_and_nominations
Revises: 0293_pbc_items_acceptance_override_reason
Create Date: 2026-07-10 00:00:00.000000

DPDP Act 2023 Section 9 requires verifiable consent of a parent/lawful guardian before
processing a child's (under 18) personal data, or of a court/authority-appointed guardian
for a person with disability who cannot act independently. DPDP Act 2023 Section 10
(DPDP Rules 2025, Rule 10) provides for nomination: a Data Principal may designate another
individual to exercise their rights in the event of death or incapacity.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0294_dpdp_consent_minor_guardian_and_nominations"
down_revision: str | None = "0293_pbc_items_acceptance_override_reason"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("consent_records", sa.Column("is_minor_or_guardian_managed", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("consent_records", sa.Column("guardian_relationship", sa.String(length=30), nullable=True))
    op.add_column("consent_records", sa.Column("guardian_identity_reference", sa.String(length=255), nullable=True))
    op.add_column("consent_records", sa.Column("guardian_verification_method", sa.String(length=50), nullable=True))
    op.add_column("consent_records", sa.Column("guardian_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        "ck_consent_records_guardian_relationship",
        "consent_records",
        "guardian_relationship IS NULL OR guardian_relationship IN ('parent', 'lawful_guardian_disability')",
    )
    op.create_check_constraint(
        "ck_consent_records_guardian_verification_method",
        "consent_records",
        "guardian_verification_method IS NULL OR guardian_verification_method IN "
        "('government_id_token', 'digilocker', 'existing_reliable_id', 'court_authority_appointment')",
    )
    op.create_index(
        "ix_consent_records_org_minor_guardian",
        "consent_records",
        ["organization_id", "is_minor_or_guardian_managed"],
    )

    op.create_table(
        "data_principal_nominations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("subject_identifier_hash", sa.String(length=64), nullable=False),
        sa.Column("nominee_user_id", sa.Uuid(), nullable=True),
        sa.Column("nominee_name", sa.String(length=255), nullable=True),
        sa.Column("nominee_contact", sa.String(length=255), nullable=True),
        sa.Column("activation_trigger", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["nominee_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("status IN ('active', 'revoked', 'activated')", name="ck_dp_nominations_status"),
        sa.CheckConstraint("activation_trigger IN ('death', 'incapacity')", name="ck_dp_nominations_activation_trigger"),
        sa.CheckConstraint(
            "nominee_user_id IS NOT NULL OR nominee_name IS NOT NULL",
            name="ck_dp_nominations_nominee_identified",
        ),
    )
    op.create_index(
        "ix_dp_nominations_org_subject_status",
        "data_principal_nominations",
        ["organization_id", "subject_identifier_hash", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_dp_nominations_org_subject_status", table_name="data_principal_nominations")
    op.drop_table("data_principal_nominations")

    op.drop_index("ix_consent_records_org_minor_guardian", table_name="consent_records")
    op.drop_constraint("ck_consent_records_guardian_verification_method", "consent_records", type_="check")
    op.drop_constraint("ck_consent_records_guardian_relationship", "consent_records", type_="check")
    op.drop_column("consent_records", "guardian_verified_at")
    op.drop_column("consent_records", "guardian_verification_method")
    op.drop_column("consent_records", "guardian_identity_reference")
    op.drop_column("consent_records", "guardian_relationship")
    op.drop_column("consent_records", "is_minor_or_guardian_managed")
