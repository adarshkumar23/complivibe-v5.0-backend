"""add declined to policy_attestation_records status

Revision ID: 0285_policy_attestation_record_declined_status
Revises: 0284_trust_center_slug_confirmed_at
Create Date: 2026-07-09 00:00:00.000000

The completion-tracking table (policy_attestation_records, aka "legacy" record in
PolicyAttestationService) only allowed status IN ('pending', 'attested', 'expired',
'exempted') -- there was no 'declined' value. PolicyAttestationService.attest() syncs
the completion-tracking row to 'attested', but decline() never synced anything to this
table at all (in part because the enum had nowhere valid to put it), so every declined
attestation stayed 'pending' forever in policy_attestation_records -- and every
dashboard/report that reads that table (employee_attestation_service, experience_service,
custom_report_generator) shows declined attestations as still outstanding.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0285_policy_attestation_record_declined_status"
down_revision: str | None = "0284_trust_center_slug_confirmed_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_policy_attestation_records_status", "policy_attestation_records", type_="check")
    op.create_check_constraint(
        "ck_policy_attestation_records_status",
        "policy_attestation_records",
        "status IN ('pending', 'attested', 'declined', 'expired', 'exempted')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_policy_attestation_records_status", "policy_attestation_records", type_="check")
    op.create_check_constraint(
        "ck_policy_attestation_records_status",
        "policy_attestation_records",
        "status IN ('pending', 'attested', 'expired', 'exempted')",
    )
